# -*- coding: utf-8 -*-
"""转写管线：把音视频文件变成字幕条目。

四个阶段：
    decode  (0% ~ 15%)   ffmpeg 解码成 16k 单声道 wav
    vad     (15% ~ 22%)  能量检测切出语音段
    asr     (22% ~ 96%)  逐段识别
    split   (96% ~ 100%) 断句 + 时间轴校准
中间只有 wav 和帧能量数组驻留内存，长音频也不会吃爆内存。
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np

from .models import AsrToken, Cue, SpeechSegment, SplitOptions
from .splitter import build_cues
from .vad import VadOptions, detect_spans, read_span
from ..audio.decoder import DecodeError, extract_wav, probe

SAMPLE_RATE = 16000


@dataclass
class TranscribeConfig:
    language: str = "auto"
    environment: str = "quiet"
    split: SplitOptions = field(default_factory=SplitOptions)
    vad: Optional[VadOptions] = None

    def vad_options(self) -> VadOptions:
        return self.vad or VadOptions.preset(self.environment)


@dataclass
class Progress:
    stage: str
    ratio: float
    message: str
    cue_count: int = 0


@dataclass
class TranscriptionResult:
    source_path: str
    duration_sec: float
    cues: List[Cue]
    segments: List[SpeechSegment]
    elapsed_sec: float
    model_name: str = ""
    wav_path: str = ""


class Cancelled(RuntimeError):
    pass


ProgressCb = Callable[[Progress], None]
CancelCb = Callable[[], bool]


def _noop_progress(_: Progress) -> None:
    pass


def _never_cancel() -> bool:
    return False


class TranscriptionPipeline:
    """一次转写任务。可复用于批量处理，引擎与 VAD 参数按需复用。"""

    def __init__(self, engine, temp_dir: Optional[str] = None) -> None:
        self._engine = engine
        self._temp_dir = temp_dir

    def run(
        self,
        source_path: str,
        config: Optional[TranscribeConfig] = None,
        progress: Optional[ProgressCb] = None,
        should_cancel: Optional[CancelCb] = None,
    ) -> TranscriptionResult:
        cfg = config or TranscribeConfig()
        cb = progress or _noop_progress
        cancel = should_cancel or _never_cancel

        if not os.path.isfile(source_path):
            raise FileNotFoundError(f"文件不存在：{source_path}")

        t0 = time.time()
        work_dir = tempfile.mkdtemp(prefix="sf_", dir=self._temp_dir)
        wav_path = os.path.join(work_dir, "audio.wav")

        try:
            # ---------- 1. 解码 ----------
            cb(Progress("decode", 0.0, "正在解码音频…"))
            info = probe(source_path)
            if not info.has_audio:
                raise DecodeError("该文件不包含音频轨道")

            def decode_cb(r: float) -> None:
                cb(Progress("decode", r * 0.15, f"正在解码音频… {r * 100:.0f}%"))

            extract_wav(source_path, wav_path, progress=decode_cb, cancel=cancel)
            if cancel():
                raise Cancelled()

            # ---------- 2. VAD ----------
            cb(Progress("vad", 0.16, "正在检测语音区间…"))
            spans, sr = detect_spans(wav_path, cfg.vad_options())
            if cancel():
                raise Cancelled()

            if not spans:
                cb(Progress("split", 1.0, "未检测到语音内容", 0))
                return TranscriptionResult(
                    source_path, info.duration_sec, [], [], time.time() - t0,
                    getattr(self._engine, "name", ""), wav_path,
                )

            # ---------- 3. 逐段识别 ----------
            cb(Progress("asr", 0.22, "正在加载识别模型…"))
            self._engine.initialize()

            segments: List[SpeechSegment] = []
            total = len(spans)
            for idx, span in enumerate(spans):
                if cancel():
                    raise Cancelled()

                audio = read_span(wav_path, span, sr)
                if audio.size < int(0.15 * sr):
                    continue

                # 能量过低的段不送识别。模型在近乎无声的片段上容易产生幻觉
                # （凭空吐出「谢谢观看」「그.」之类），提前挡掉比事后过滤可靠。
                rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)) + 1e-12)
                if 20 * np.log10(rms) < -50.0:
                    continue

                try:
                    result = self._engine.transcribe(audio, sr)
                except Exception as exc:  # 单段失败不终止整任务
                    result = None
                    _ = exc

                if result and result.text.strip():
                    segments.append(
                        SpeechSegment(
                            start_sec=span.start_sample / sr,
                            end_sec=span.end_sample / sr,
                            text=result.text.strip(),
                            tokens=result.tokens,
                        )
                    )

                ratio = 0.22 + 0.74 * (idx + 1) / total
                cb(
                    Progress(
                        "asr",
                        min(0.96, ratio),
                        f"正在识别… {idx + 1}/{total} 段",
                        len(segments),
                    )
                )

            # ---------- 4. 断句 ----------
            cb(Progress("split", 0.97, "正在断句与对齐时间轴…", len(segments)))
            cues = build_cues(segments, cfg.split)
            cb(Progress("split", 1.0, f"完成，共 {len(cues)} 条字幕", len(cues)))

            return TranscriptionResult(
                source_path=source_path,
                duration_sec=info.duration_sec,
                cues=cues,
                segments=segments,
                elapsed_sec=time.time() - t0,
                model_name=getattr(self._engine, "name", ""),
                wav_path=wav_path,
            )
        finally:
            # 保留 wav 供播放器试听，由调用方决定何时删除
            pass

    @staticmethod
    def cleanup(wav_path: str) -> None:
        """删除临时 wav 及其目录。"""
        if not wav_path:
            return
        try:
            d = os.path.dirname(wav_path)
            if os.path.isdir(d) and os.path.basename(d).startswith("sf_"):
                shutil.rmtree(d, ignore_errors=True)
            elif os.path.isfile(wav_path):
                os.remove(wav_path)
        except OSError:
            pass


# ---------------------------------------------------------------- 兜底引擎

class DemoEngine:
    """无模型时的演示引擎。

    不产生真实识别结果，只按音频时长生成占位字幕，用于在没有模型的机器上
    验证「导入 → 解码 → 断句 → 导出」全链路是否正常。
    """

    name = "演示引擎（无模型）"

    _SAMPLE = [
        "这是一段用于验证流程的占位文本。",
        "检测到模型未安装，当前使用演示引擎。",
        "请把模型放到 models 目录后重新开始。",
        "导出的 SRT 和 TXT 格式与正式结果完全一致。",
        "时间轴按音频长度均匀分配。",
    ]

    def __init__(self) -> None:
        self._inited = False

    @property
    def ready(self) -> bool:
        return self._inited

    def initialize(self, progress=None) -> None:
        self._inited = True
        if progress:
            progress(1.0, "演示引擎就绪")

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000):
        from ..asr.base import AsrResult

        dur = len(samples) / max(1, sample_rate)
        text = self._SAMPLE[int(dur * 10) % len(self._SAMPLE)]

        # 按字符均分时间，生成 token
        tokens: List[AsrToken] = []
        per = dur / max(1, len(text))
        for i, ch in enumerate(text):
            tokens.append(AsrToken(ch, i * per, (i + 1) * per))
        return AsrResult(text, tokens, "zh")

    def release(self) -> None:
        self._inited = False

# -*- coding: utf-8 -*-
"""语音活动检测（VAD）。

用双门限能量检测实现。相比调用神经网络 VAD，这个方案有三个好处：
  * 时间戳精确到 10ms（帧级），可直接作为时间轴锚点；
  * 无额外模型依赖，打包体积小；
  * 参数可解释，便于按场景调优。

处理流程分两遍：
  第一遍逐块读音频，只记录每 10ms 一帧的能量（内存占用与音频长度无关，
  1 小时音频约 1.4MB）；
  第二遍用全段能量分布估计噪声底，再跑状态机切出语音段。
"""
from __future__ import annotations

import wave
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np


@dataclass
class VadOptions:
    """VAD 参数。UI 上的「环境类型」下拉框映射到这里的预设。"""

    frame_ms: int = 25
    hop_ms: int = 10
    enter_db: float = -30.0        # 进入语音的绝对阈值
    exit_margin_db: float = 8.0    # 退出阈值 = 进入阈值 - 该值（滞回，防抖）
    noise_offset_db: float = 10.0  # 相对噪声底的偏移
    min_speech_ms: int = 200       # 短于此的段丢弃（咳嗽、翻页）
    min_silence_ms: int = 350      # 静音超过此值判定段结束
    max_speech_ms: int = 30000     # 单段上限，超出强制切
    pad_ms: int = 120              # 段前后留白，避免吃掉字头字尾

    @classmethod
    def preset(cls, env: str) -> "VadOptions":
        """按使用环境返回预设参数。"""
        base = cls()
        if env == "meeting":
            base.min_silence_ms = 250
            base.max_speech_ms = 20000
            base.enter_db = -32.0
        elif env == "outdoor":
            base.enter_db = -24.0
            base.noise_offset_db = 12.0
            base.min_silence_ms = 500
        elif env == "dialogue":
            base.min_silence_ms = 200
            base.max_speech_ms = 15000
            base.enter_db = -30.0
        elif env == "lecture":
            base.min_silence_ms = 400
            base.max_speech_ms = 30000
        return base


@dataclass(slots=True)
class SpeechSpan:
    """语音段的样本索引区间。"""

    start_sample: int
    end_sample: int

    @property
    def length(self) -> int:
        return self.end_sample - self.start_sample


def _read_wav_info(path: str) -> Tuple[int, int, int, int]:
    """返回 (采样率, 声道数, 采样位宽, 总帧数)。"""
    with wave.open(path, "rb") as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()


def _iter_wav_chunks(path: str, chunk_sec: float = 60.0):
    """逐块读出 float32 单声道样本。"""
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        chunk_frames = int(sr * chunk_sec)
        while True:
            raw = w.readframes(chunk_frames)
            if not raw:
                break
            if sw == 2:
                arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            elif sw == 4:
                arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
            elif sw == 1:
                arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
            else:
                raise ValueError(f"不支持的采样位宽：{sw * 8} bit")
            if ch > 1:
                arr = arr.reshape(-1, ch).mean(axis=1)
            yield arr


def frame_energies(samples: np.ndarray, frame_len: int, hop: int) -> np.ndarray:
    """计算每帧的 RMS 能量（dBFS）。"""
    if len(samples) < frame_len:
        if len(samples) == 0:
            return np.empty(0, dtype=np.float32)
        rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
        return np.array([20 * np.log10(max(rms, 1e-7))], dtype=np.float32)

    n_frames = 1 + (len(samples) - frame_len) // hop
    idx = np.arange(n_frames) * hop
    # 用 stride 视图避免复制，再按帧求均方
    windows = np.lib.stride_tricks.sliding_window_view(samples, frame_len)[idx]
    ms = np.mean(windows.astype(np.float32) ** 2, axis=1)
    return (10.0 * np.log10(np.maximum(ms, 1e-14))).astype(np.float32)


def collect_frame_db(wav_path: str, opt: VadOptions) -> Tuple[np.ndarray, int]:
    """第一遍：扫全片，返回 (每帧 dB 数组, 采样率)。"""
    sr, _, _, _ = _read_wav_info(wav_path)
    frame_len = max(1, int(sr * opt.frame_ms / 1000))
    hop = max(1, int(sr * opt.hop_ms / 1000))

    parts: List[np.ndarray] = []
    carry = np.empty(0, dtype=np.float32)

    for chunk in _iter_wav_chunks(wav_path):
        buf = np.concatenate([carry, chunk]) if carry.size else chunk
        if len(buf) < frame_len:
            carry = buf
            continue
        parts.append(frame_energies(buf, frame_len, hop))
        # 保留最后一个不完整帧需要的样本，保证帧跨块连续
        consumed = 1 + (len(buf) - frame_len) // hop
        used = consumed * hop
        carry = buf[used:]

    if carry.size >= frame_len:
        parts.append(frame_energies(carry, frame_len, hop))

    if not parts:
        return np.empty(0, dtype=np.float32), sr
    return np.concatenate(parts), sr


def _estimate_noise_floor(db: np.ndarray) -> float:
    """用 15% 分位数估计噪声底。假设至少 15% 的时间是静音。"""
    if db.size == 0:
        return -60.0
    return float(np.percentile(db, 15))


def detect_spans(wav_path: str, opt: VadOptions | None = None) -> Tuple[List[SpeechSpan], int]:
    """检测语音段，返回 (段列表, 采样率)。"""
    opt = opt or VadOptions()
    db, sr = collect_frame_db(wav_path, opt)
    if db.size == 0:
        return [], sr

    hop = max(1, int(sr * opt.hop_ms / 1000))
    frame_len = max(1, int(sr * opt.frame_ms / 1000))

    noise = _estimate_noise_floor(db)
    enter = max(opt.enter_db, noise + opt.noise_offset_db)
    exit_th = enter - opt.exit_margin_db

    min_speech_frames = max(1, int(opt.min_speech_ms / opt.hop_ms))
    min_silence_frames = max(1, int(opt.min_silence_ms / opt.hop_ms))
    max_speech_frames = max(1, int(opt.max_speech_ms / opt.hop_ms))
    pad_frames = max(0, int(opt.pad_ms / opt.hop_ms))

    spans: List[SpeechSpan] = []
    in_speech = False
    seg_start = 0
    silence_run = 0

    for i in range(db.size):
        e = float(db[i])
        if not in_speech:
            if e >= enter:
                in_speech = True
                seg_start = i
                silence_run = 0
        else:
            if e < exit_th:
                silence_run += 1
                if silence_run >= min_silence_frames:
                    seg_end = i - silence_run + 1
                    _emit(spans, seg_start, seg_end, min_speech_frames,
                          max_speech_frames, pad_frames, hop, frame_len, sr)
                    in_speech = False
                    silence_run = 0
            else:
                silence_run = 0
                if i - seg_start >= max_speech_frames:
                    _emit(spans, seg_start, i, min_speech_frames,
                          max_speech_frames, pad_frames, hop, frame_len, sr)
                    in_speech = False
                    silence_run = 0

    if in_speech:
        _emit(spans, seg_start, db.size - 1, min_speech_frames,
              max_speech_frames, pad_frames, hop, frame_len, sr)

    return _merge_spans(spans, hop, sr), sr


def _emit(
    spans: List[SpeechSpan],
    start_frame: int,
    end_frame: int,
    min_speech_frames: int,
    max_speech_frames: int,
    pad_frames: int,
    hop: int,
    frame_len: int,
    sr: int,
) -> None:
    """把帧区间转成样本区间并做长度过滤与超长切分。"""
    if end_frame <= start_frame:
        return
    length_frames = end_frame - start_frame

    # 超长段强制切成等长小块，避免单次推理过长
    if length_frames > max_speech_frames:
        pieces = int(np.ceil(length_frames / max_speech_frames))
        step = length_frames // pieces
        for k in range(pieces):
            s = start_frame + k * step
            e = start_frame + (k + 1) * step if k < pieces - 1 else end_frame
            _emit(spans, s, e, min_speech_frames, max_speech_frames, pad_frames,
                  hop, frame_len, sr)
        return

    if length_frames < min_speech_frames:
        return

    s = max(0, (start_frame - pad_frames) * hop)
    e = (end_frame + pad_frames) * hop + frame_len
    spans.append(SpeechSpan(int(s), int(e)))


def _merge_spans(spans: List[SpeechSpan], hop: int, sr: int) -> List[SpeechSpan]:
    """合并因留白而重叠的相邻段。"""
    if not spans:
        return []
    spans.sort(key=lambda x: x.start_sample)
    out = [spans[0]]
    for cur in spans[1:]:
        last = out[-1]
        if cur.start_sample <= last.end_sample:
            out[-1] = SpeechSpan(last.start_sample, max(last.end_sample, cur.end_sample))
        else:
            out.append(cur)
    return out


def read_span(wav_path: str, span: SpeechSpan, sample_rate: int) -> np.ndarray:
    """从 wav 中读取指定样本区间，返回 float32 单声道。"""
    with wave.open(wav_path, "rb") as w:
        ch = w.getnchannels()
        sw = w.getsampwidth()
        w.setpos(max(0, span.start_sample))
        n = max(0, span.end_sample - span.start_sample)
        raw = w.readframes(n)
    if sw == 2:
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    if ch > 1:
        arr = arr.reshape(-1, ch).mean(axis=1)
    return arr

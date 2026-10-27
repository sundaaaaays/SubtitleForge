# -*- coding: utf-8 -*-
"""基于 sherpa-onnx 的 SenseVoice 识别引擎。

SenseVoice-Small 的优势：自带标点、自带逆文本规范化（把「二零二六年」
转成「2026年」）、支持中英日韩粤、CPU 上约 15~20 倍实时。
"""
from __future__ import annotations

import os
import threading
from typing import List, Optional

import numpy as np

from ..core.models import AsrToken
from .base import AsrEngine, AsrResult, AsrUnavailable

_LANG_MAP = {
    "auto": "auto",
    "zh": "zh",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "yue": "yue",
}


class SenseVoiceEngine(AsrEngine):
    """线程安全的 SenseVoice 封装。模型只加载一次，之后复用。"""

    name = "sherpa-onnx / SenseVoice"

    def __init__(
        self,
        model_path: str,
        tokens_path: str,
        language: str = "auto",
        num_threads: int = 4,
        use_itn: bool = True,
    ) -> None:
        self._model_path = model_path
        self._tokens_path = tokens_path
        self._language = _LANG_MAP.get(language, "auto")
        self._num_threads = max(1, int(num_threads))
        self._use_itn = use_itn
        self._rec = None
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- 生命周期

    @property
    def ready(self) -> bool:
        return self._rec is not None

    def initialize(self, progress=None) -> None:
        if self._rec is not None:
            return
        if not os.path.isfile(self._model_path):
            raise AsrUnavailable(f"模型文件不存在：{self._model_path}")
        if not os.path.isfile(self._tokens_path):
            raise AsrUnavailable(f"词表文件不存在：{self._tokens_path}")

        try:
            import sherpa_onnx
        except ImportError as e:
            raise AsrUnavailable(f"未安装 sherpa-onnx：{e}") from e

        if progress:
            progress(0.1, "正在加载模型…")

        self._rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=self._model_path,
            tokens=self._tokens_path,
            num_threads=self._num_threads,
            use_itn=self._use_itn,
            language=self._language,
            debug=False,
        )

        if progress:
            progress(1.0, "模型就绪")

    def release(self) -> None:
        with self._lock:
            self._rec = None

    # ---------------------------------------------------------------- 识别

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> AsrResult:
        if self._rec is None:
            raise AsrUnavailable("模型尚未加载")
        if samples.size == 0:
            return AsrResult("", [], self._language)

        # sherpa-onnx 的 stream 不是线程安全的，加锁串行化
        with self._lock:
            stream = self._rec.create_stream()
            stream.accept_waveform(sample_rate, samples.astype(np.float32))
            self._rec.decode_stream(stream)
            result = stream.result

        text = (result.text or "").strip()
        tokens = self._build_tokens(result)
        lang = getattr(result, "lang", "") or self._language
        emotion = getattr(result, "emotion", "") or ""
        return AsrResult(text, tokens, _clean_tag(lang), _clean_tag(emotion))

    @staticmethod
    def _build_tokens(result) -> List[AsrToken]:
        """把 token 起始时间列表转成 [start, end] 区间。

        SenseVoice 只给每个 token 的起始时刻，结束时刻用下一个 token 的起点补。
        末个 token 没有后继，按平均时长外推。
        """
        raw_tokens = list(getattr(result, "tokens", []) or [])
        raw_ts = list(getattr(result, "timestamps", []) or [])
        if not raw_tokens or not raw_ts:
            return []

        n = min(len(raw_tokens), len(raw_ts))
        avg = 0.18
        if n >= 2:
            span = raw_ts[n - 1] - raw_ts[0]
            if span > 0:
                avg = max(0.05, min(0.6, span / (n - 1)))

        out: List[AsrToken] = []
        for i in range(n):
            text = raw_tokens[i]
            if not text or text.startswith("<|"):
                continue
            start = float(raw_ts[i])
            end = float(raw_ts[i + 1]) if i + 1 < n else start + avg
            if end <= start:
                end = start + avg
            out.append(AsrToken(text, start, end))
        return out


def _clean_tag(tag: str) -> str:
    """把 ``<|zh|>`` 这类标记清洗成 ``zh``。"""
    if not tag:
        return ""
    t = tag.strip()
    if t.startswith("<|") and t.endswith("|>"):
        t = t[2:-2]
    return t.strip()

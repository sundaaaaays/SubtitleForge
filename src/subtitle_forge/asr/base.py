# -*- coding: utf-8 -*-
"""ASR 引擎接口与结果类型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Protocol, runtime_checkable

import numpy as np

from ..core.models import AsrToken


@dataclass
class AsrResult:
    text: str
    tokens: List[AsrToken] = field(default_factory=list)
    language: str = ""
    emotion: str = ""


@runtime_checkable
class AsrEngine(Protocol):
    """语音识别引擎。时间戳相对本次输入音频的起点。"""

    name: str

    def initialize(self, progress=None) -> None:
        ...

    def transcribe(self, samples: np.ndarray, sample_rate: int = 16000) -> AsrResult:
        ...

    def release(self) -> None:
        ...

    @property
    def ready(self) -> bool:
        ...


class AsrUnavailable(RuntimeError):
    pass

# -*- coding: utf-8 -*-
"""核心数据模型。全部为纯 Python，不依赖 Qt / numpy。"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import List


@dataclass(slots=True)
class AsrToken:
    """识别模型输出的一个最小文本单元，时间相对本次输入音频的起点。"""

    text: str
    start_sec: float
    end_sec: float


@dataclass(slots=True)
class SpeechSegment:
    """VAD 切出的一段连续语音。时间已换算为全局绝对时间。"""

    start_sec: float
    end_sec: float
    text: str = ""
    tokens: List[AsrToken] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end_sec - self.start_sec


@dataclass(slots=True)
class Cue:
    """一条字幕。时间用毫秒整数，避免浮点累积误差。"""

    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def shifted(self, delta_ms: int) -> "Cue":
        return replace(self, start_ms=self.start_ms + delta_ms, end_ms=self.end_ms + delta_ms)


@dataclass
class SplitOptions:
    """断句参数。默认值与开发文档第 6 章一致。"""

    max_chars: int = 18
    max_duration_sec: float = 6.0
    min_duration_sec: float = 0.8
    silence_gap_sec: float = 0.6
    min_gap_ms: int = 80
    break_on_punctuation: bool = True
    drop_fillers: bool = False
    wrap_lines: bool = False
    max_line_chars: int = 20

    def validate(self) -> None:
        self.max_chars = max(4, min(60, int(self.max_chars)))
        self.max_duration_sec = max(1.0, min(30.0, float(self.max_duration_sec)))
        self.min_duration_sec = max(0.2, min(float(self.max_duration_sec), float(self.min_duration_sec)))
        self.silence_gap_sec = max(0.1, min(5.0, float(self.silence_gap_sec)))
        self.min_gap_ms = max(0, min(2000, int(self.min_gap_ms)))


# 语速估计：中文约 4.5 字/秒，英文约 12 字符/秒。
# 用于在断句时约束「这条字幕至少需要显示多久才能读完」。
CHARS_PER_SECOND = 4.5


@dataclass
class ExportOptions:
    """导出参数。"""

    formats: List[str] = field(default_factory=lambda: ["srt", "txt"])
    start_index: int = 1
    encoding: str = "utf-8-sig"      # utf-8-sig / utf-8 / gb18030 / utf-16
    newline: str = "\r\n"            # "\r\n" 或 "\n"
    # TXT 专用
    txt_layout: str = "line"         # line / continuous / paragraph / timestamp
    paragraph_size: int = 5
    keep_punctuation: bool = True
    with_timestamp: bool = False
    add_serial: bool = False

    def resolved_layout(self) -> str:
        return "timestamp" if self.with_timestamp else self.txt_layout

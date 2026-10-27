# -*- coding: utf-8 -*-
"""字幕导出：SRT / WebVTT / TXT。

所有 Render 函数只做字符串生成，不碰 IO，便于单元测试与快照比对。
"""
from __future__ import annotations

import os
from typing import Callable, Dict, List, Sequence

from .models import Cue, ExportOptions
from .textutil import (
    ms_to_short,
    ms_to_srt,
    ms_to_vtt,
    strip_punctuation,
    wrap_two_lines,
)


class SubtitleWriter:
    """导出器基类。"""

    format_id: str = ""
    extension: str = ""

    def render(self, cues: Sequence[Cue], opt: ExportOptions) -> str:
        raise NotImplementedError


# ---------------------------------------------------------------- SRT

class SrtWriter(SubtitleWriter):
    """SubRip。毫秒必须用逗号，小时必须两位，条目间必须空行。"""

    format_id = "srt"
    extension = ".srt"

    def render(self, cues: Sequence[Cue], opt: ExportOptions) -> str:
        nl = opt.newline
        blocks: List[str] = []
        for i, c in enumerate(cues):
            text = c.text
            if opt.formats and "wrap" in opt.formats:
                text = wrap_two_lines(text, 20)
            text = text.replace("\n", nl)
            blocks.append(
                f"{opt.start_index + i}{nl}"
                f"{ms_to_srt(c.start_ms)} --> {ms_to_srt(c.end_ms)}{nl}"
                f"{text}"
            )
        return (nl + nl).join(blocks) + (nl + nl if blocks else "")


# ---------------------------------------------------------------- VTT

class VttWriter(SubtitleWriter):
    """WebVTT。时间码用点号分隔毫秒，无序号，首行必须是 WEBVTT。"""

    format_id = "vtt"
    extension = ".vtt"

    def render(self, cues: Sequence[Cue], opt: ExportOptions) -> str:
        nl = opt.newline
        lines = ["WEBVTT", ""]
        for c in cues:
            lines.append(f"{ms_to_vtt(c.start_ms)} --> {ms_to_vtt(c.end_ms)}")
            lines.append(c.text.replace("\n", nl))
            lines.append("")
        return nl.join(lines)


# ---------------------------------------------------------------- TXT

class TxtWriter(SubtitleWriter):
    """纯文本。四种排版 × 三个开关，覆盖笔记、语料、通读等场景。"""

    format_id = "txt"
    extension = ".txt"

    def render(self, cues: Sequence[Cue], opt: ExportOptions) -> str:
        nl = opt.newline
        texts = [self._transform(c.text, opt) for c in cues]
        layout = opt.resolved_layout()

        if layout == "timestamp":
            body = self._with_timestamp(cues, texts, nl, opt)
        elif layout == "continuous":
            body = "".join(texts)
        elif layout == "paragraph":
            body = self._paragraphs(texts, max(1, opt.paragraph_size), nl, opt)
        else:
            body = nl.join(texts)

        return body + nl if body else ""

    @staticmethod
    def _transform(text: str, opt: ExportOptions) -> str:
        t = text
        if not opt.keep_punctuation:
            t = strip_punctuation(t)
        return t.strip()

    @staticmethod
    def _paragraphs(texts: List[str], size: int, nl: str, opt: ExportOptions) -> str:
        blocks = []
        for start in range(0, len(texts), size):
            chunk = texts[start:start + size]
            if opt.add_serial:
                head = f"{start // size + 1}. "
            else:
                head = ""
            blocks.append(head + "".join(chunk))
        return (nl + nl).join(blocks)

    @staticmethod
    def _with_timestamp(
        cues: Sequence[Cue], texts: List[str], nl: str, opt: ExportOptions
    ) -> str:
        lines = []
        for i, (c, t) in enumerate(zip(cues, texts)):
            prefix = f"[{ms_to_short(c.start_ms)}] "
            if opt.add_serial:
                prefix = f"{i + 1}. " + prefix
            lines.append(prefix + t)
        return nl.join(lines)


# ---------------------------------------------------------------- 注册表

WRITERS: Dict[str, SubtitleWriter] = {
    "srt": SrtWriter(),
    "vtt": VttWriter(),
    "txt": TxtWriter(),
}


def get_writer(fmt: str) -> SubtitleWriter | None:
    return WRITERS.get(fmt.lower().strip().lstrip("."))


def render(fmt: str, cues: Sequence[Cue], opt: ExportOptions) -> str:
    w = get_writer(fmt)
    if w is None:
        raise ValueError(f"不支持的格式：{fmt}")
    return w.render(cues, opt)


# ---------------------------------------------------------------- 落盘

def unique_path(directory: str, base_name: str, ext: str, overwrite: bool = False) -> str:
    """同名文件冲突时追加 _1 / _2 后缀。"""
    path = os.path.join(directory, base_name + ext)
    if overwrite or not os.path.exists(path):
        return path
    for i in range(1, 1000):
        candidate = os.path.join(directory, f"{base_name}_{i}{ext}")
        if not os.path.exists(candidate):
            return candidate
    raise IOError("无法生成唯一文件名")


def write_file(path: str, content: str, encoding: str = "utf-8-sig") -> str:
    """按指定编码写文件，保留内容里原有的换行符。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding=encoding, newline="") as f:
        f.write(content)
    return path


def export(
    cues: Sequence[Cue],
    opt: ExportOptions,
    source_path: str,
    out_dir: str | None = None,
    overwrite: bool = False,
    progress: Callable[[str], None] | None = None,
) -> List[str]:
    """按选项导出全部格式，返回写出的文件路径列表。"""
    base = os.path.splitext(os.path.basename(source_path))[0]
    directory = out_dir or os.path.dirname(os.path.abspath(source_path))
    written: List[str] = []

    for fmt in opt.formats:
        fmt = fmt.lower().strip().lstrip(".")
        writer = get_writer(fmt)
        if writer is None:
            continue
        content = writer.render(cues, opt)
        path = unique_path(directory, base, writer.extension, overwrite)
        write_file(path, content, opt.encoding)
        written.append(path)
        if progress:
            progress(path)
    return written


# ---------------------------------------------------------------- 校验

def validate(cues: Sequence[Cue]) -> List[str]:
    """导出前检查，返回问题描述列表（不阻断导出）。"""
    problems: List[str] = []
    for i, c in enumerate(cues):
        if c.end_ms <= c.start_ms:
            problems.append(f"第 {i + 1} 条：结束时间不大于开始时间")
        elif c.end_ms - c.start_ms < 200:
            problems.append(f"第 {i + 1} 条：时长短于 200ms，可能来不及显示")
        if i > 0 and c.start_ms < cues[i - 1].end_ms:
            problems.append(f"第 {i + 1} 条：与上一条时间重叠")
        if not c.text.strip():
            problems.append(f"第 {i + 1} 条：文本为空")
    return problems

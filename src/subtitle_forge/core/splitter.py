# -*- coding: utf-8 -*-
"""断句与时间轴构建。

输入 VAD 切出的语音段（含 token 级时间戳），输出规整的 Cue 列表。

算法分三层：
  1. 绝对化 + 线性规整 —— 把 token 的相对时间映射到全局时间，并用 VAD 段边界
     作为锚点拉伸，消除模型时间戳的累积漂移。
  2. 段内贪心断句 —— 按「句末标点 > 分号 > 静音间隔 > 长度 > 时长」的优先级切分。
  3. 全局后处理 —— 合并过短条目、强制时间单调、补最小间隔。
"""
from __future__ import annotations

from dataclasses import replace
from typing import List, Sequence

from .models import AsrToken, Cue, SpeechSegment, SplitOptions
from .textutil import (
    COMMA,
    SEMI,
    SENTENCE_END,
    char_boundaries,
    clean_text,
    concat_text,
    visual_width,
)

# 单条字幕最少需要显示多久（毫秒），低于此值观众读不完
_MIN_VISIBLE_MS = 700
# 合并短条目时，单条时长的硬上限
_FORCE_SPLIT_DURATION = 12.0

# 字符集合预计算，避免在内层循环里反复做字符串包含判断
SENTENCE_END_SET = frozenset(SENTENCE_END)
SEMI_SET = frozenset(SEMI)
COMMA_SET = frozenset(COMMA)


# ---------------------------------------------------------------- 时间轴校准

def absolutize(seg: SpeechSegment, tokens: Sequence[AsrToken]) -> List[AsrToken]:
    """把 token 的相对时间换算为全局时间，并线性规整到段边界。

    VAD 段边界来自能量检测，通常比模型内部对齐准（误差 < 50ms）。
    用准确的边界去拉伸不准的内部时间戳，能把「累积漂移」压成「局部抖动」。
    """
    if not tokens:
        return []

    dur = max(seg.end_sec - seg.start_sec, 0.001)
    t_first = tokens[0].start_sec
    t_last = tokens[-1].end_sec
    span = t_last - t_first

    if span > 0.05:
        k = dur / span
        # 缩放系数异常说明模型时间戳不可信，退化为整体平移
        if not (0.5 <= k <= 2.5):
            k = 1.0
        base = seg.start_sec
    else:
        k = 1.0
        base = seg.start_sec

    out: List[AsrToken] = []
    for t in tokens:
        s = base + (t.start_sec - t_first) * k
        e = base + (t.end_sec - t_first) * k
        if e <= s:
            e = s + 0.05
        out.append(AsrToken(t.text, s, e))

    # 裁剪到段边界内，防止越界
    lo, hi = seg.start_sec, seg.end_sec
    for i, t in enumerate(out):
        out[i] = AsrToken(t.text, min(max(t.start_sec, lo), hi), min(max(t.end_sec, lo), hi))
    return out


# ---------------------------------------------------------------- 段内断句

def _token_width_accum(tokens: Sequence[AsrToken]) -> float:
    return sum(visual_width(t.text) for t in tokens)


def _last_char(tokens: Sequence[AsrToken]) -> str:
    for t in reversed(tokens):
        s = t.text.rstrip()
        if s:
            return s[-1]
    return ""


def _find_cut(tokens: Sequence[AsrToken], start: int, opt: SplitOptions) -> int:
    """从 start 开始累积，返回切点下标（不含）。保证返回值 > start。

    决策顺序（与开发文档 6.2 的信号优先级一致）：
      P0 句末标点 → P1 分号 → P2 静音间隔 → P5 长度超限 → P6 时长超限
    其中 P5/P6 触发时会先向前找「最近的句末标点」顺延过去，避免把一句话
    腰斩在毫无意义的位置。
    """
    n = len(tokens)
    width = 0.0
    i = start

    while i < n:
        tok = tokens[i]
        width += visual_width(tok.text)
        ch = tok.text.rstrip()[-1:] if tok.text.strip() else ""

        # P0 句末标点
        if opt.break_on_punctuation and ch and ch in SENTENCE_END_SET:
            return i + 1

        # P1 分号
        if opt.break_on_punctuation and ch and ch in SEMI_SET:
            return i + 1

        # P2 静音间隔（要看下一个 token）
        if i + 1 < n:
            gap = tokens[i + 1].start_sec - tok.end_sec
            if gap >= opt.silence_gap_sec and width >= 4.0:
                return i + 1

        # P5 长度超限
        if width > opt.max_chars:
            ahead = _look_ahead_sentence_end(tokens, i, opt.max_chars * 1.15 - width)
            if ahead is not None:
                return ahead
            return _best_cut(tokens, start, i, opt.max_chars)

        # P6 时长超限。要求宽度也达到上限的一半，否则说明时间戳与文本长度
        # 不成比例（模型时间戳失真），此时按时间切会把句子切得极碎。
        dur = tok.end_sec - tokens[start].start_sec
        if dur > opt.max_duration_sec and width >= opt.max_chars * 0.8:
            return _best_cut(tokens, start, i, opt.max_chars)

        i += 1

    return n


def _look_ahead_sentence_end(
    tokens: Sequence[AsrToken], from_idx: int, budget_width: float
) -> int | None:
    """从 from_idx 往后看几个 token，若很快遇到句末标点就顺延到其后。"""
    if budget_width <= 0:
        return None
    acc = 0.0
    n = len(tokens)
    for j in range(from_idx + 1, min(n, from_idx + 8)):
        acc += visual_width(tokens[j].text)
        if acc > budget_width:
            return None
        tail = tokens[j].text.rstrip()[-1:] if tokens[j].text.strip() else ""
        if tail and tail in SENTENCE_END_SET:
            return j + 1
    return None


def _best_cut(
    tokens: Sequence[AsrToken], start: int, last: int, max_chars: int
) -> int:
    """在 [start, last] 区间内选一个尽量均衡、语义合理的切点。

    优先用「后半段里的逗号」，其次按词边界，最后退化为 last。
    """
    if last <= start:
        return start + 1
    span = last - start

    # 1) 后半段的逗号，避免像「大家好，」这种超短条目
    lower = start + max(2, int(span * 0.45))
    for j in range(last, lower - 1, -1):
        tail = tokens[j].text.rstrip()[-1:] if tokens[j].text.strip() else ""
        if tail and tail in COMMA_SET:
            return j + 1

    # 2) 词边界
    wb = _find_word_boundary(tokens, start, last, max_chars)
    if wb is not None and wb - start >= 1:
        return wb + 1

    # 3) 兜底
    return last if last > start else start + 1


def _find_word_boundary(
    tokens: Sequence[AsrToken], start: int, end: int, max_chars: int
):
    """按累计视觉宽度找切点，优先不切在英文单词中间。"""
    text = "".join(t.text for t in tokens[start:end + 1])
    allowed = char_boundaries(text)

    best = None
    acc = 0.0
    pos = 0
    for idx in range(start, end + 1):
        acc += visual_width(tokens[idx].text)
        pos += len(tokens[idx].text)
        if acc > max_chars:
            break
        if pos in allowed or idx == start:
            best = idx
    return best


def _make_cue(tokens: Sequence[AsrToken], opt: SplitOptions) -> Cue | None:
    text_parts = []
    for t in tokens:
        if t.text and not t.text.startswith("<|"):
            text_parts.append(t.text)
    text = clean_text("".join(text_parts), opt.drop_fillers)
    if not text:
        return None

    start_ms = int(round(tokens[0].start_sec * 1000))
    end_ms = int(round(tokens[-1].end_sec * 1000))
    if end_ms <= start_ms:
        end_ms = start_ms + 200

    return Cue(index=0, start_ms=start_ms, end_ms=end_ms, text=text)


def _effective_options(text: str, opt: SplitOptions) -> SplitOptions:
    """英文为主的文本放宽长度上限。

    视觉宽度的定义是「ASCII 字符占半个汉字宽」，所以 18 的上限对英文只等于
    36 个字符，会把 "called for the / boy" 这种短语硬切开。英文按字面宽度
    天然就窄，放宽一倍后一行大约 70 字符，符合阅读习惯。
    """
    if not text:
        return opt
    latin = sum(1 for c in text if ord(c) < 0x80 and not c.isspace())
    visible = sum(1 for c in text if not c.isspace())
    if visible and latin / visible > 0.7:
        return replace(opt, max_chars=int(opt.max_chars * 2))
    return opt


def split_segment(seg: SpeechSegment, opt: SplitOptions) -> List[Cue]:
    """对单个语音段做断句。"""
    opt = _effective_options(seg.text, opt)
    tokens = absolutize(seg, seg.tokens)
    if not tokens:
        # 没有 token 时间戳时，退化为整段一条
        text = clean_text(seg.text, opt.drop_fillers)
        if not text:
            return []
        return [Cue(0, int(seg.start_sec * 1000), int(seg.end_sec * 1000), text)]

    cues: List[Cue] = []
    i = 0
    n = len(tokens)
    while i < n:
        cut = _find_cut(tokens, i, opt)
        if cut <= i:
            cut = i + 1
        cue = _make_cue(tokens[i:cut], opt)
        if cue is not None:
            cues.append(cue)
        i = cut
    return cues


# ---------------------------------------------------------------- 全局后处理

def merge_short_cues(cues: List[Cue], opt: SplitOptions) -> List[Cue]:
    """合并过短或过碎的条目，避免屏幕上闪一下就消失。"""
    if not cues:
        return []

    out: List[Cue] = []
    i = 0
    n = len(cues)
    while i < n:
        cur = cues[i]
        while i + 1 < n:
            nxt = cues[i + 1]
            too_short = (
                cur.duration_ms < opt.min_duration_sec * 1000
                or visual_width(cur.text) < 3.0
            )
            if not too_short:
                break
            merged_w = visual_width(cur.text) + visual_width(nxt.text)
            merged_d = (nxt.end_ms - cur.start_ms) / 1000.0
            if merged_w > opt.max_chars or merged_d > max(opt.max_duration_sec, _FORCE_SPLIT_DURATION):
                break
            cur = Cue(0, cur.start_ms, nxt.end_ms, concat_text(cur.text, nxt.text))
            i += 1
        out.append(cur)
        i += 1
    return out


def _ensure_readable_time(cues: List[Cue]) -> List[Cue]:
    """保证每条字幕有足够的阅读时间：按字数估算所需时长，不够则延长结束时间。"""
    out: List[Cue] = []
    for idx, c in enumerate(cues):
        need_ms = int(visual_width(c.text) / 4.5 * 1000)
        need_ms = max(need_ms, _MIN_VISIBLE_MS)
        end = c.end_ms
        if end - c.start_ms < need_ms:
            limit = cues[idx + 1].start_ms if idx + 1 < len(cues) else c.start_ms + need_ms
            end = min(c.start_ms + need_ms, max(limit, c.start_ms + _MIN_VISIBLE_MS))
        out.append(Cue(idx + 1, c.start_ms, max(end, c.start_ms + 300), c.text))
    return out


def enforce_monotonic(cues: List[Cue], min_gap_ms: int) -> List[Cue]:
    """强制时间轴单调不重叠。播放器遇到时间倒退会丢字幕。"""
    out: List[Cue] = []
    prev_end = -1
    for c in cues:
        start = c.start_ms
        if start < prev_end + min_gap_ms:
            start = prev_end + min_gap_ms
        end = max(c.end_ms, start + 300)
        out.append(Cue(c.index, start, end, c.text))
        prev_end = end
    return out


# ---------------------------------------------------------------- 入口

def build_cues(
    segments: Sequence[SpeechSegment],
    opt: SplitOptions | None = None,
) -> List[Cue]:
    """主入口：语音段 → 字幕条目。"""
    opt = opt or SplitOptions()
    opt.validate()

    raw: List[Cue] = []
    for seg in segments:
        raw.extend(split_segment(seg, opt))

    if not raw:
        return []

    merged = merge_short_cues(raw, opt)
    readable = _ensure_readable_time(merged)
    final = enforce_monotonic(readable, opt.min_gap_ms)

    # 重新编号
    return [Cue(i + 1, c.start_ms, c.end_ms, c.text) for i, c in enumerate(final)]


def segments_from_text(text: str, duration_sec: float) -> List[SpeechSegment]:
    """无 ASR 时的兜底：把整段文本按时间均匀铺开，用于 UI 演示与测试。"""
    if not text.strip():
        return []
    t = clean_text(text)
    return [SpeechSegment(0.0, duration_sec, t, [])]

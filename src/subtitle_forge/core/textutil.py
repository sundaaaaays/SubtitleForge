# -*- coding: utf-8 -*-
"""文本与时间码工具：视觉宽度、标点规范化、词边界、时间码格式化。

全部为纯函数，无副作用，便于单元测试。
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List

# ---------------------------------------------------------------- 时间码

def ms_to_srt(ms: int) -> str:
    """毫秒 → SRT 时间码 ``HH:MM:SS,mmm``（小时 2 位，毫秒用逗号）。"""
    if ms < 0:
        ms = 0
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, msec = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{msec:03d}"


def ms_to_vtt(ms: int) -> str:
    """毫秒 → WebVTT 时间码 ``HH:MM:SS.mmm``。"""
    return ms_to_srt(ms).replace(",", ".")


def ms_to_short(ms: int) -> str:
    """毫秒 → 短时间码。不足 1 小时输出 ``MM:SS``，否则 ``HH:MM:SS``。"""
    if ms < 0:
        ms = 0
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s = rem // 1000
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse_timecode(text: str) -> int:
    """解析 ``HH:MM:SS,mmm`` / ``MM:SS`` 等格式为毫秒，失败返回 -1。"""
    text = text.strip().replace(".", ",")
    m = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:,(\d{1,3}))?", text)
    if not m:
        return -1
    h = int(m.group(1) or 0)
    mi = int(m.group(2))
    se = int(m.group(3))
    frac = m.group(4) or "0"
    msec = int(frac.ljust(3, "0")[:3])
    return ((h * 60 + mi) * 60 + se) * 1000 + msec


# ---------------------------------------------------------------- 视觉宽度

def char_width(ch: str) -> float:
    """单个字符的视觉宽度。中文全角记 1.0，ASCII 记 0.5。"""
    cp = ord(ch)
    if cp < 0x80:
        return 0.5
    if 0x4E00 <= cp <= 0x9FFF:      # CJK 统一汉字
        return 1.0
    if 0x3400 <= cp <= 0x4DBF:      # 扩展 A
        return 1.0
    if 0x3000 <= cp <= 0x303F:      # CJK 标点
        return 1.0
    if 0xFF00 <= cp <= 0xFFEF:      # 全角
        return 1.0
    if 0x3040 <= cp <= 0x30FF:      # 日文假名
        return 1.0
    if 0xAC00 <= cp <= 0xD7AF:      # 韩文
        return 1.0
    return 0.6


def visual_width(text: str) -> float:
    """整段文本的视觉宽度，用于判断字幕是否超屏。"""
    return sum(char_width(c) for c in text)


# ---------------------------------------------------------------- 标点

# 句末标点（最强断点）
SENTENCE_END = "。！？!?…"
# 次级断点
SEMI = "；;"
# 弱断点
COMMA = "，,、：:"
# 全部标点
PUNCT_ALL = SENTENCE_END + SEMI + COMMA + "“”‘’《》〈〉「」『』（）()[]【】—～·\"'"

_NUMBER_RE = re.compile(r"\d[\d,]*([.:]\d+)*")
_CJK_LATIN_RE = re.compile(
    r"([\u4e00-\u9fff\u3040-\u30ff])([A-Za-z0-9])|([A-Za-z0-9])([\u4e00-\u9fff\u3040-\u30ff])"
)


def normalize_punctuation(text: str) -> str:
    """半角标点转全角，同时保护数字中的 ``.`` ``,`` ``:``。

    不做替换会破坏 ``3.14`` / ``10:30`` / ``1,000``，所以先把数字整体
    替换成占位符，处理完再还原。
    """
    if not text:
        return text

    holders: list[str] = []

    def _stash(m: re.Match) -> str:
        holders.append(m.group(0))
        return f"\x01{len(holders) - 1}\x01"

    protected = _NUMBER_RE.sub(_stash, text)

    table = str.maketrans({
        ",": "，", ".": "。", "?": "？", "!": "！",
        ";": "；", ":": "：",
    })
    protected = protected.translate(table)

    for i, original in enumerate(holders):
        protected = protected.replace(f"\x01{i}\x01", original)
    return protected


def strip_punctuation(text: str) -> str:
    """删除所有标点，得到纯净文本（用于 NLP 语料导出）。"""
    return "".join(c for c in text if c not in PUNCT_ALL)


def add_cjk_latin_space(text: str) -> str:
    """在中文与英文/数字之间补一个空格，符合中文排版规范。"""
    return _CJK_LATIN_RE.sub(
        lambda m: f"{m.group(1)} {m.group(2)}" if m.group(1) else f"{m.group(3)} {m.group(4)}",
        text,
    )


# ---------------------------------------------------------------- 分词边界

_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_HAN_RE = re.compile(r"[\u4e00-\u9fff]")


def char_boundaries(text: str) -> set[int]:
    """计算允许断行的字符位置集合。

    规则：
      - 中文可以逐字断（汉字之间天然是合法断点）
      - 英文/数字必须整词断，不能切在单词中间
      - 标点之后是合法断点
    返回的是「可以在该下标处切开」的位置集合（不含 0 和 len）。
    """
    n = len(text)
    ok: set[int] = set()
    if n <= 1:
        return ok

    # 标记英文/数字词的内部位置为非法
    locked: set[int] = set()
    for m in _WORD_RE.finditer(text):
        for i in range(m.start() + 1, m.end()):
            locked.add(i)

    for i in range(1, n):
        if i in locked:
            continue
        prev_ch, cur_ch = text[i - 1], text[i]
        # 标点之后可断
        if prev_ch in PUNCT_ALL:
            ok.add(i)
            continue
        # 汉字与任何东西相邻都可断
        if _HAN_RE.match(prev_ch) or _HAN_RE.match(cur_ch):
            ok.add(i)
            continue
        # 空格之后可断
        if prev_ch in " \t":
            ok.add(i)
    return ok


# ---------------------------------------------------------------- 清理

_FILLERS = {"嗯", "呃", "啊", "哦", "唉", "呀", "额", "唔"}
_FILLER_WORDS = {"那个", "就是说", "然后就是"}

_WHITESPACE_RE = re.compile(r"[ \t\u3000]+")


def normalize_whitespace(text: str) -> str:
    """压缩连续空白，去掉首尾。"""
    return _WHITESPACE_RE.sub(" ", text).strip()


def is_filler(text: str) -> bool:
    """判断是否为纯语气词（去掉标点后）。"""
    core = strip_punctuation(text).strip()
    return core in _FILLERS or core in _FILLER_WORDS


def clean_text(text: str, drop_fillers: bool = False) -> str:
    """基础清理：去首尾空白、压缩重复标点。"""
    if not text:
        return ""
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = re.sub(r"([，。！？；：])\1+", r"\1", text)
    text = normalize_whitespace(text)
    if drop_fillers and is_filler(text):
        return ""
    return text


def concat_text(a: str, b: str) -> str:
    """拼接两段文本。中文直接拼，两个 ASCII 词之间补空格。"""
    if not a:
        return b
    if not b:
        return a
    last, first = a[-1], b[0]
    if ord(last) < 0x80 and ord(first) < 0x80 and not last.isspace() and last not in PUNCT_ALL:
        return f"{a} {b}"
    return a + b


def wrap_two_lines(text: str, max_chars: int) -> str:
    """把过长的字幕折成两行，在中间附近找标点或词边界断。"""
    if max_chars <= 0 or visual_width(text) <= max_chars:
        return text

    n = len(text)
    mid = n // 2
    allowed = char_boundaries(text)

    best = mid
    for offset in range(0, n // 3):
        for cand in (mid + offset, mid - offset):
            if 1 <= cand <= n - 1 and cand in allowed:
                best = cand
                break
        else:
            continue
        break

    left, right = text[:best].rstrip(), text[best:].lstrip()
    if not left or not right:
        return text
    return f"{left}\n{right}"


def join_cues_text(texts: Iterable[str]) -> str:
    """把多条文本拼成一段（中文无空格）。"""
    out = ""
    for t in texts:
        out = concat_text(out, t)
    return out


def display_width_ratio(text: str) -> float:
    """返回占宽比，用于 UI 上的超长提示。"""
    return visual_width(text) / 18.0


# ---------------------------------------------------------------- 语言

_CJK_ANY_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def guess_language(text: str) -> str:
    """粗略判断文本语言，用于导出时决定是否补空格。"""
    cjk = len(_CJK_ANY_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    if cjk and latin:
        return "mixed"
    if cjk:
        return "zh"
    if latin:
        return "en"
    return "unknown"


def unicode_len(text: str) -> int:
    """按 Unicode 码点计长度（emoji 不会被当成两个字符）。"""
    return len(unicodedata.normalize("NFC", text))

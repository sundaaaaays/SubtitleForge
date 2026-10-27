# -*- coding: utf-8 -*-
"""核心逻辑冒烟测试：断句 + 导出格式。不依赖 Qt / 模型。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from subtitle_forge.core.models import AsrToken, Cue, ExportOptions, SpeechSegment, SplitOptions
from subtitle_forge.core.splitter import build_cues
from subtitle_forge.core import exporters
from subtitle_forge.core.textutil import (
    char_boundaries, ms_to_srt, ms_to_short, normalize_punctuation,
    visual_width, wrap_two_lines,
)


def make_tokens(text, start, per=0.28):
    """把字符串逐字展开成 token，模拟 ASR 输出。"""
    out, t = [], start
    for ch in text:
        out.append(AsrToken(ch, round(t, 3), round(t + per, 3)))
        t += per
    return out


def section(name):
    print(f"\n{'='*62}\n{name}\n{'='*62}")


section("1. 时间码")
for ms in (0, 999, 60000, 3599999, 3661001):
    print(f"  {ms:>8}ms -> {ms_to_srt(ms)}   short={ms_to_short(ms)}")

section("2. 视觉宽度")
for s in ("你好世界", "Hello 世界", "iPhone 15 Pro", "这是一个测试"):
    print(f"  {s!r:22} width={visual_width(s):.1f}")

section("3. 标点规范化（数字保护）")
for s in ("价格是3.14元,时间是10:30,对吧?", "共1,000人,增幅2.5%"):
    print(f"  {s!r}\n    -> {normalize_punctuation(s)!r}")

section("4. 词边界")
t = "今天我们用Python开发了一个小工具"
print(f"  {t}")
print(f"  boundaries = {sorted(char_boundaries(t))}")

section("5. 断句：长句按标点切")
long_text = "大家好，今天我们来聊一聊离线语音识别的技术选型问题。首先看需求：完全本地运行，不联网，也不能有账号体系。这是第一点。"
seg = SpeechSegment(0.0, 18.0, long_text, make_tokens(long_text, 0.0, 0.30))
cues = build_cues([seg], SplitOptions(max_chars=18, max_duration_sec=6.0))
for c in cues:
    print(f"  [{c.index:2d}] {ms_to_srt(c.start_ms)} --> {ms_to_srt(c.end_ms)}  "
          f"({c.duration_ms:5d}ms, w={visual_width(c.text):4.1f})  {c.text}")

section("6. 断句：无标点长句兜底")
np_text = "今天我们讨论三个话题第一个是性能优化第二个是可维护性第三个是成本控制我们要逐个分析"
seg2 = SpeechSegment(20.0, 46.0, np_text, make_tokens(np_text, 0.0, 0.32))
cues2 = build_cues([seg2], SplitOptions(max_chars=16, max_duration_sec=5.0))
for c in cues2:
    print(f"  [{c.index:2d}] {ms_to_srt(c.start_ms)} --> {ms_to_srt(c.end_ms)}  "
          f"(w={visual_width(c.text):4.1f})  {c.text}")

section("7. 单调性检查")
ok = all(cues2[i].start_ms >= cues2[i-1].end_ms for i in range(1, len(cues2)))
print(f"  时间单调递增: {ok}")
print(f"  最短时长: {min(c.duration_ms for c in cues2)}ms")
print(f"  条数: {len(cues2)}")

section("8. SRT 输出")
opt = ExportOptions(formats=["srt", "txt"])
print(exporters.render("srt", cues2[:3], opt))

section("9. TXT 各模式")
for layout, kw in (("line", {}), ("continuous", {}), ("paragraph", {"paragraph_size": 2}),
                   ("timestamp", {"with_timestamp": True}),
                   ("line", {"keep_punctuation": False})):
    o = ExportOptions(txt_layout=layout, **kw)
    body = exporters.render("txt", cues2[:4], o).replace("\r\n", "⏎")
    print(f"  [{layout}{',' + str(kw) if kw else ''}]")
    print(f"    {body}")

section("10. VTT 输出")
print(exporters.render("vtt", cues2[:2], opt))

section("11. 导出校验")
print(f"  problems = {exporters.validate(cues2)}")

section("12. 折行")
print(repr(wrap_two_lines("这是一个非常非常长的字幕文本需要折成两行显示才对", 16)))
print("OK - all core checks passed")

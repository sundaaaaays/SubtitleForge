# -*- coding: utf-8 -*-
"""核心逻辑单元测试。运行：python -m unittest discover -s tests -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from subtitle_forge.core import exporters
from subtitle_forge.core.models import (
    AsrToken,
    Cue,
    ExportOptions,
    SpeechSegment,
    SplitOptions,
)
from subtitle_forge.core.splitter import build_cues, merge_short_cues
from subtitle_forge.core.textutil import (
    char_boundaries,
    concat_text,
    ms_to_short,
    ms_to_srt,
    normalize_punctuation,
    parse_timecode,
    strip_punctuation,
    visual_width,
    wrap_two_lines,
)


def make_tokens(text: str, start: float = 0.0, per: float = 0.22):
    out = []
    t = start
    for ch in text:
        out.append(AsrToken(ch, round(t, 4), round(t + per, 4)))
        t += per
    return out


class TestTimecode(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(ms_to_srt(0), "00:00:00,000")

    def test_millis(self):
        self.assertEqual(ms_to_srt(999), "00:00:00,999")

    def test_minutes(self):
        self.assertEqual(ms_to_srt(60_000), "00:01:00,000")

    def test_hours_two_digits(self):
        self.assertEqual(ms_to_srt(3_661_001), "01:01:01,001")

    def test_negative_clamped(self):
        self.assertEqual(ms_to_srt(-500), "00:00:00,000")

    def test_comma_not_dot(self):
        # SRT 规范要求毫秒用逗号，用点号会被多数播放器拒绝
        self.assertIn(",", ms_to_srt(1234))
        self.assertNotIn(".", ms_to_srt(1234))

    def test_short_format(self):
        self.assertEqual(ms_to_short(65_000), "01:05")
        self.assertEqual(ms_to_short(3_725_000), "1:02:05")

    def test_parse_roundtrip(self):
        for ms in (0, 1500, 65_432, 3_600_000):
            self.assertEqual(parse_timecode(ms_to_srt(ms)), ms)

    def test_parse_invalid(self):
        self.assertEqual(parse_timecode("abc"), -1)


class TestVisualWidth(unittest.TestCase):
    def test_chinese_counts_one(self):
        self.assertAlmostEqual(visual_width("你好世界"), 4.0)

    def test_ascii_counts_half(self):
        self.assertAlmostEqual(visual_width("abcd"), 2.0)

    def test_mixed(self):
        # 5 个 ASCII(2.5) + 空格(0.5) + 2 个汉字(2.0)
        self.assertAlmostEqual(visual_width("Hello 世界"), 5.0)

    def test_empty(self):
        self.assertEqual(visual_width(""), 0.0)


class TestPunctuation(unittest.TestCase):
    def test_halfwidth_to_fullwidth(self):
        self.assertEqual(normalize_punctuation("你好,世界?"), "你好，世界？")

    def test_decimal_protected(self):
        self.assertEqual(normalize_punctuation("价格3.14元"), "价格3.14元")

    def test_time_colon_protected(self):
        self.assertIn("10:30", normalize_punctuation("时间10:30开会"))

    def test_thousand_separator(self):
        self.assertIn("1,000", normalize_punctuation("共1,000人"))

    def test_strip(self):
        self.assertEqual(strip_punctuation("你好，世界！"), "你好世界")

    def test_concat_chinese_no_space(self):
        self.assertEqual(concat_text("你好", "世界"), "你好世界")

    def test_concat_ascii_adds_space(self):
        self.assertEqual(concat_text("hello", "world"), "hello world")

    def test_char_boundaries_keep_words(self):
        # "Python" 内部不允许断
        bs = char_boundaries("用Python开发")
        self.assertNotIn(2, bs)
        self.assertNotIn(3, bs)


class TestSplitter(unittest.TestCase):
    def test_sentence_end_splits(self):
        text = "第一句话。第二句话。"
        seg = SpeechSegment(0.0, 4.0, text, make_tokens(text, 0.0, 0.25))
        cues = build_cues([seg])
        self.assertEqual(len(cues), 2)
        self.assertTrue(cues[0].text.endswith("。"))

    def test_monotonic(self):
        text = "今天我们来聊一聊离线语音识别的技术选型问题以及具体的实现方案。"
        seg = SpeechSegment(0.0, 12.0, text, make_tokens(text, 0.0, 0.3))
        cues = build_cues([seg], SplitOptions(max_chars=12))
        for i in range(1, len(cues)):
            self.assertGreaterEqual(cues[i].start_ms, cues[i - 1].end_ms)

    def test_max_chars_respected(self):
        text = "这些汉字没有标点所以只能靠长度来切分这个句子会变得很长很长"
        seg = SpeechSegment(0.0, 10.0, text, make_tokens(text, 0.0, 0.2))
        cues = build_cues([seg], SplitOptions(max_chars=10))
        for c in cues:
            # 允许 1.15 倍容差（为了顺延到句末标点）
            self.assertLessEqual(visual_width(c.text), 10 * 1.2)

    def test_no_empty_cue(self):
        text = "嗯。啊。好。"
        seg = SpeechSegment(0.0, 2.0, text, make_tokens(text, 0.0, 0.3))
        cues = build_cues([seg])
        for c in cues:
            self.assertTrue(c.text.strip())

    def test_end_after_start(self):
        seg = SpeechSegment(5.0, 5.2, "短", make_tokens("短", 0.0, 0.2))
        cues = build_cues([seg])
        for c in cues:
            self.assertGreater(c.end_ms, c.start_ms)

    def test_english_wider_limit(self):
        # 英文按字面宽度天然更窄，应该自动放宽到 2 倍
        text = "The tribal chieftain called for the boy and presented him with gold."
        seg = SpeechSegment(0.0, 6.0, text, make_tokens(text, 0.0, 0.1))
        cues = build_cues([seg], SplitOptions(max_chars=18))
        self.assertLessEqual(len(cues), 3)

    def test_empty_segment(self):
        self.assertEqual(build_cues([]), [])

    def test_merge_short(self):
        cues = [
            Cue(1, 0, 200, "嗯"),
            Cue(2, 220, 1500, "这是主体内容"),
        ]
        merged = merge_short_cues(cues, SplitOptions(max_chars=30))
        self.assertEqual(len(merged), 1)
        self.assertIn("这是主体内容", merged[0].text)

    def test_absolute_timing(self):
        # 段的起始时间必须体现在结果里
        text = "测试。"
        seg = SpeechSegment(30.0, 31.0, text, make_tokens(text, 0.0, 0.4))
        cues = build_cues([seg])
        self.assertGreaterEqual(cues[0].start_ms, 29_000)
        self.assertLessEqual(cues[0].end_ms, 31_500)


class TestExporters(unittest.TestCase):
    def setUp(self):
        self.cues = [
            Cue(1, 1000, 3500, "你好，世界。"),
            Cue(2, 3800, 7200, "这是第二句字幕。"),
        ]

    def test_srt_structure(self):
        out = exporters.render("srt", self.cues, ExportOptions())
        self.assertTrue(out.startswith("1\r\n00:00:01,000 --> 00:00:03,500\r\n"))
        self.assertIn("\r\n\r\n2\r\n", out)
        self.assertTrue(out.endswith("\r\n\r\n"))

    def test_srt_start_index(self):
        out = exporters.render("srt", self.cues, ExportOptions(start_index=5))
        self.assertTrue(out.startswith("5\r\n"))

    def test_srt_lf_newline(self):
        out = exporters.render("srt", self.cues, ExportOptions(newline="\n"))
        self.assertNotIn("\r\n", out)

    def test_vtt_header(self):
        out = exporters.render("vtt", self.cues, ExportOptions())
        self.assertTrue(out.startswith("WEBVTT"))
        self.assertIn("00:00:01.000 --> 00:00:03.500", out)

    def test_txt_line(self):
        out = exporters.render("txt", self.cues, ExportOptions()).replace("\r\n", "\n")
        self.assertEqual(out, "你好，世界。\n这是第二句字幕。\n")

    def test_txt_continuous(self):
        out = exporters.render(
            "txt", self.cues, ExportOptions(txt_layout="continuous")
        ).replace("\r\n", "\n")
        self.assertEqual(out, "你好，世界。这是第二句字幕。\n")

    def test_txt_paragraph(self):
        cues = [Cue(i, i * 1000, i * 1000 + 800, f"第{i}句。") for i in range(1, 5)]
        out = exporters.render(
            "txt", cues, ExportOptions(txt_layout="paragraph", paragraph_size=2)
        ).replace("\r\n", "\n")
        self.assertIn("\n\n", out)

    def test_txt_timestamp(self):
        out = exporters.render(
            "txt", self.cues, ExportOptions(with_timestamp=True)
        ).replace("\r\n", "\n")
        self.assertTrue(out.startswith("[00:01] "))

    def test_txt_strip_punctuation(self):
        out = exporters.render(
            "txt", self.cues, ExportOptions(keep_punctuation=False)
        )
        self.assertNotIn("，", out)
        self.assertNotIn("。", out)

    def test_validate_catches_overlap(self):
        bad = [Cue(1, 0, 2000, "a"), Cue(2, 1000, 3000, "b")]
        self.assertTrue(exporters.validate(bad))

    def test_validate_ok(self):
        self.assertEqual(exporters.validate(self.cues), [])

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            exporters.render("doc", self.cues, ExportOptions())


class TestWrap(unittest.TestCase):
    def test_short_text_untouched(self):
        self.assertEqual(wrap_two_lines("短句", 20), "短句")

    def test_long_text_wrapped(self):
        text = "这是一个非常长的字幕文本需要折成两行才能完整显示"
        out = wrap_two_lines(text, 12)
        self.assertIn("\n", out)
        self.assertEqual(out.replace("\n", ""), text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

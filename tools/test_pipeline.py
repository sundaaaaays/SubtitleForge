# -*- coding: utf-8 -*-
"""端到端测试：真实音频 → 解码 → VAD → 识别 → 断句 → 导出。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from subtitle_forge.asr.sensevoice import SenseVoiceEngine
from subtitle_forge.core.models import ExportOptions, SplitOptions
from subtitle_forge.core.pipeline import TranscribeConfig, TranscriptionPipeline
from subtitle_forge.core import exporters
from subtitle_forge.core.textutil import ms_to_srt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODEL = os.path.join(ROOT, "models", "sensevoice", "model.int8.onnx")
TOKENS = os.path.join(ROOT, "models", "sensevoice", "tokens.txt")


def run(path, label):
    print(f"\n{'='*64}\n{label}: {os.path.basename(path)}\n{'='*64}")
    engine = SenseVoiceEngine(MODEL, TOKENS, language="auto", num_threads=4)
    pipe = TranscriptionPipeline(engine)

    last = [""]

    def on_progress(p):
        line = f"  [{p.stage:7s}] {p.ratio*100:5.1f}%  {p.message}  (cues={p.cue_count})"
        if line != last[0]:
            print(line)
            last[0] = line

    cfg = TranscribeConfig(split=SplitOptions(max_chars=18, max_duration_sec=6.0))
    result = pipe.run(path, cfg, progress=on_progress)

    print(f"\n  时长 {result.duration_sec:.2f}s  耗时 {result.elapsed_sec:.2f}s  "
          f"RTF {result.duration_sec/max(result.elapsed_sec,1e-6):.1f}x")
    print(f"  语音段 {len(result.segments)} 个  字幕 {len(result.cues)} 条\n")
    for c in result.cues:
        print(f"    [{c.index:2d}] {ms_to_srt(c.start_ms)} --> {ms_to_srt(c.end_ms)}  {c.text}")

    opt = ExportOptions()
    print("\n  --- SRT ---")
    print("  " + exporters.render("srt", result.cues, opt).replace("\n", "\n  ").rstrip())
    print("\n  --- TXT (timestamp) ---")
    print("  " + exporters.render("txt", result.cues,
                                   ExportOptions(with_timestamp=True)).replace("\n", "\n  ").rstrip())

    # 断言基本不变量
    assert result.cues, "应当产生字幕"
    for i in range(1, len(result.cues)):
        assert result.cues[i].start_ms >= result.cues[i-1].end_ms, "时间轴必须单调"
    for c in result.cues:
        assert c.end_ms > c.start_ms, "结束时间必须大于开始时间"
        assert c.text.strip(), "文本不能为空"
    print(f"\n  ✓ 不变量检查通过")

    pipe.cleanup(result.wav_path)
    return result


if __name__ == "__main__":
    run(os.path.join(ROOT, "testdata", "zh.wav"), "中文")
    run(os.path.join(ROOT, "testdata", "en.wav"), "英文")
    print("\n全部通过")

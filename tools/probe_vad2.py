# -*- coding: utf-8 -*-
"""逐 512 样本喂入，用 is_speech_detected 的翻转点作为段边界，测量精度。"""
import wave
import numpy as np
import sherpa_onnx

WIN = 512


def read_wav(path):
    with wave.open(path, "rb") as w:
        sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        arr = arr.reshape(-1, ch).mean(axis=1)
    return arr, sr


samples, sr = read_wav("testdata/zh.wav")
pad = np.zeros(2 * sr, dtype=np.float32)
combo = np.concatenate([pad, samples, pad])

truth_start = 2 * sr
truth_end = 2 * sr + len(samples)
print(f"真实: start={truth_start} ({truth_start/sr:.3f}s)  end={truth_end} ({truth_end/sr:.3f}s)")

for min_sil in (0.35, 0.25, 0.5):
    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = "models/silero_vad.onnx"
    cfg.silero_vad.threshold = 0.5
    cfg.silero_vad.min_silence_duration = min_sil
    cfg.silero_vad.min_speech_duration = 0.2
    cfg.silero_vad.max_speech_duration = 30.0
    cfg.silero_vad.window_size = WIN
    cfg.sample_rate = sr
    cfg.num_threads = 1
    vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)

    prev = False
    rises, falls = [], []
    n = len(combo)
    # 补齐到 WIN 的整数倍
    padlen = (-n) % WIN
    if padlen:
        combo2 = np.concatenate([combo, np.zeros(padlen, dtype=np.float32)])
    else:
        combo2 = combo

    fed = 0
    for i in range(0, len(combo2), WIN):
        vad.accept_waveform(combo2[i:i + WIN])
        fed = i + WIN
        cur = vad.is_speech_detected()
        if cur and not prev:
            rises.append(i)          # 窗口起点
        elif not cur and prev:
            falls.append(fed)        # 窗口终点
        prev = cur

    print(f"\nmin_silence={min_sil}")
    for r in rises:
        print(f"  上升沿 @ {r:6d} ({r/sr:7.3f}s)  误差 {(r-truth_start)/sr*1000:+7.0f} ms")
    for f in falls:
        corrected = f - int(min_sil * sr)
        print(f"  下降沿 @ {f:6d} ({f/sr:7.3f}s)  减min_sil后误差 {(corrected-truth_end)/sr*1000:+7.0f} ms")

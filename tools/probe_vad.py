# -*- coding: utf-8 -*-
"""精确探测 VAD segment 的字段语义：构造已知结构的音频，看边界如何对应。"""
import wave
import numpy as np
import sherpa_onnx


def read_wav(path):
    with wave.open(path, "rb") as w:
        sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        arr = arr.reshape(-1, ch).mean(axis=1)
    return arr, sr


def make_vad(sr):
    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = "models/silero_vad.onnx"
    cfg.silero_vad.threshold = 0.5
    cfg.silero_vad.min_silence_duration = 0.35
    cfg.silero_vad.min_speech_duration = 0.2
    cfg.silero_vad.max_speech_duration = 30.0
    cfg.silero_vad.window_size = 512
    cfg.sample_rate = sr
    cfg.num_threads = 1
    return sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)


samples, sr = read_wav("testdata/zh.wav")
print(f"speech wav: {len(samples)/sr:.3f}s, {len(samples)} samples")

# 构造：2s 静音 + 语音 + 2s 静音 + 语音(前2秒) + 2s 静音
pad = np.zeros(2 * sr, dtype=np.float32)
combo = np.concatenate([pad, samples, pad, samples[:2 * sr], pad])

# 语音真实起点（样本索引）
truth = [
    (2 * sr, 2 * sr + len(samples)),
    (2 * sr + len(samples) + 2 * sr, 2 * sr + len(samples) + 2 * sr + 2 * sr),
]
print("真实语音区间(samples):", truth)
print("真实语音区间(sec):", [(round(a / sr, 3), round(b / sr, 3)) for a, b in truth])

vad = make_vad(sr)
for i in range(0, len(combo), sr):
    vad.accept_waveform(combo[i:i + sr])
vad.flush()

print("\n--- segments ---")
k = 0
while not vad.empty():
    seg = vad.front
    attrs = [a for a in dir(seg) if not a.startswith("_")]
    start = seg.start
    smp = np.array(seg.samples, copy=True) if hasattr(seg, "samples") else None
    nsamp = len(smp) if smp is not None else -1
    print(f"[{k}] attrs={attrs}")
    print(f"    start={start}  samples_len={nsamp}")
    print(f"    start_as_sec={start/sr:.3f}")
    if k < len(truth):
        t0, t1 = truth[k]
        print(f"    真实起点={t0/sr:.3f}s ({t0}), 真实终点={t1/sr:.3f}s ({t1})")
        print(f"    start 与真实起点差 = {(start - t0)/sr:+.3f}s")
        print(f"    start+len 与真实终点差 = {((start+nsamp) - t1)/sr:+.3f}s")
        if smp is not None and nsamp > 0:
            corr = np.corrcoef(smp[:min(len(smp), len(samples))],
                               samples[:min(len(smp), len(samples))])[0, 1]
            print(f"    与源音频相关系数 = {corr:.4f}  (接近1说明samples就是该段音频)")
    vad.pop()
    k += 1

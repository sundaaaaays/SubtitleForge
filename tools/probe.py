# -*- coding: utf-8 -*-
"""原型验证：VAD + SenseVoice 识别，确认 sherpa-onnx 2.0 的实际 API 与返回字段。"""
import sys, time, wave
import numpy as np
import sherpa_onnx


def read_wav(path):
    with wave.open(path, "rb") as w:
        sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if sw == 2:
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width {sw}")
    if ch > 1:
        arr = arr.reshape(-1, ch).mean(axis=1)
    return arr, sr


def main():
    t0 = time.time()
    rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model="models/sensevoice/model.int8.onnx",
        tokens="models/sensevoice/tokens.txt",
        num_threads=4,
        use_itn=True,
        language="auto",
        debug=False,
    )
    print(f"[1] recognizer loaded in {time.time()-t0:.2f}s")

    samples, sr = read_wav("testdata/zh.wav")
    print(f"[2] audio: {len(samples)/sr:.2f}s @ {sr}Hz")

    # --- 单段识别 ---
    t1 = time.time()
    stream = rec.create_stream()
    stream.accept_waveform(sr, samples)
    rec.decode_stream(stream)
    r = stream.result
    el = time.time() - t1
    print(f"[3] decode ok in {el:.2f}s  (RTF {len(samples)/sr/el:.1f}x)")
    print(f"    text       = {r.text!r}")
    print(f"    lang       = {getattr(r, 'lang', 'N/A')!r}")
    print(f"    emotion    = {getattr(r, 'emotion', 'N/A')!r}")
    ts = getattr(r, "timestamps", None)
    tks = getattr(r, "tokens", None)
    print(f"    has timestamps = {ts is not None}, type={type(ts)}")
    if ts:
        print(f"    ts[0:8]    = {[round(x, 3) for x in ts[:8]]}")
        print(f"    ts[-3:]    = {[round(x, 3) for x in ts[-3:]]}")
        print(f"    ts monotonic = {all(ts[i] <= ts[i+1] for i in range(len(ts)-1))}")
        print(f"    ts max     = {max(ts):.3f}  (audio dur {len(samples)/sr:.3f})")
    if tks:
        print(f"    tokens[:12]= {list(tks[:12])}")

    # --- VAD 验证 ---
    print("[4] VAD ...")
    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = "models/silero_vad.onnx"
    cfg.silero_vad.threshold = 0.5
    cfg.silero_vad.min_silence_duration = 0.35
    cfg.silero_vad.min_speech_duration = 0.2
    cfg.silero_vad.max_speech_duration = 30.0
    cfg.silero_vad.window_size = 512
    cfg.sample_rate = sr
    cfg.num_threads = 1

    vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)
    # 用 1 秒块的静音 + 语音 + 静音拼一段，观察 segment.start 语义
    pad = np.zeros(sr, dtype=np.float32)
    combo = np.concatenate([pad, samples, pad])
    for i in range(0, len(combo), sr):
        vad.accept_waveform(combo[i:i + sr])
    vad.flush()
    segs = []
    while not vad.empty():
        s = vad.front
        segs.append(s)
        vad.pop()
    print(f"    segments = {len(segs)}")
    for s in segs:
        st = getattr(s, "start", None)
        nsamp = len(getattr(s, "samples", []))
        print(f"      start={st} (type {type(st).__name__})  samples={nsamp} ({nsamp/sr:.2f}s)")
        if st is not None:
            print(f"      -> as samples: {st/sr:.3f}s / as seconds: {st:.3f}s")

    # --- 分块多次识别，检查时间戳是否相对本次输入 ---
    print("[5] chunked recognition (2 chunks) ...")
    half = len(samples) // 2
    for idx, chunk in enumerate([samples[:half], samples[half:]]):
        st = rec.create_stream()
        st.accept_waveform(sr, chunk)
        rec.decode_stream(st)
        rr = st.result
        tsx = getattr(rr, "timestamps", [])
        print(f"    chunk{idx}: text={rr.text[:30]!r} ts_range="
              f"{round(min(tsx),2) if tsx else None}~{round(max(tsx),2) if tsx else None}")


if __name__ == "__main__":
    main()

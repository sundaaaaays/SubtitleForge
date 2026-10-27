# -*- coding: utf-8 -*-
"""FFmpeg 解码封装。

核心思路：不自己实现解码器和重采样，直接让 ffmpeg 把任意音视频转成
16kHz / 单声道 / 16bit PCM 的 wav，后续所有环节只处理这一种格式。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Optional

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2})\.(\d+)")
_AUDIO_STREAM_RE = re.compile(r"Stream #\d+:\d+.*: Audio:")


class FfmpegNotFound(RuntimeError):
    pass


class DecodeError(RuntimeError):
    pass


def find_ffmpeg() -> str:
    """定位 ffmpeg 可执行文件。

    优先用程序目录下的 ffmpeg.exe（打包时随包分发），其次用 imageio-ffmpeg
    自带的那份（开发环境），最后尝试 PATH。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(here))), "ffmpeg.exe"),
        os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe"),
        os.path.join(os.path.dirname(os.path.dirname(here)), "ffmpeg.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    from shutil import which

    found = which("ffmpeg")
    if found:
        return found
    raise FfmpegNotFound(
        "未找到 ffmpeg.exe。请把它放到程序目录下，或安装 imageio-ffmpeg。"
    )


@dataclass
class MediaInfo:
    duration_sec: float
    has_audio: bool
    raw_summary: str = ""


def _startupinfo() -> "subprocess.STARTUPINFO | None":
    if os.name != "nt":
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return si


def _run(args: list, timeout: Optional[float] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        startupinfo=_startupinfo(),
        encoding="utf-8",
        errors="replace",
    )


def probe(media_path: str) -> MediaInfo:
    """读取时长与是否含音轨。ffmpeg 把这两项信息都写在 stderr。"""
    ffmpeg = find_ffmpeg()
    proc = _run([ffmpeg, "-hide_banner", "-nostdin", "-i", media_path], timeout=60)
    text = proc.stderr or ""

    duration = 0.0
    m = _DURATION_RE.search(text)
    if m:
        h, mi, s, frac = m.groups()
        duration = int(h) * 3600 + int(mi) * 60 + int(s) + float("0." + frac)

    has_audio = bool(_AUDIO_STREAM_RE.search(text))
    return MediaInfo(duration, has_audio, text[-2000:])


def extract_wav(
    src: str,
    dst: str,
    progress: Optional[Callable[[float], None]] = None,
    cancel: Optional[Callable[[], bool]] = None,
) -> str:
    """把任意音视频转成 16kHz 单声道 s16le wav。返回输出路径。"""
    ffmpeg = find_ffmpeg()
    info = probe(src)
    if not info.has_audio:
        raise DecodeError("该文件不包含音频轨道")

    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)

    args = [
        ffmpeg,
        "-hide_banner", "-nostdin", "-y",
        "-loglevel", "error",
        "-i", src,
        "-vn", "-sn", "-dn",
        "-map", "0:a:0",
        "-ac", "1",
        "-ar", "16000",
        "-acodec", "pcm_s16le",
        "-progress", "pipe:1",
        "-nostats",
        dst,
    ]

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        startupinfo=_startupinfo(),
    )

    total = max(info.duration_sec, 0.1)
    last_err = ""

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us=") and progress:
                try:
                    us = int(line.split("=", 1)[1])
                    progress(min(0.999, (us / 1_000_000) / total))
                except ValueError:
                    pass
            elif line.startswith("out_time_ms=") and progress:
                # 老版本 ffmpeg 的 out_time_ms 实际是微秒，这里兜底
                try:
                    us = int(line.split("=", 1)[1])
                    progress(min(0.999, (us / 1_000_000) / total))
                except ValueError:
                    pass
            elif line.startswith("progress=end"):
                if progress:
                    progress(1.0)
            if cancel and cancel():
                proc.kill()
                raise DecodeError("已取消")

        proc.wait(timeout=30)
        if proc.returncode != 0:
            last_err = (proc.stderr.read() if proc.stderr else "") or ""
            raise DecodeError(f"解码失败（ffmpeg 返回 {proc.returncode}）：{last_err[-500:]}")
    finally:
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

    if not os.path.isfile(dst) or os.path.getsize(dst) < 1000:
        raise DecodeError("解码结果为空，请确认文件未损坏")

    if progress:
        progress(1.0)
    return dst


AUDIO_EXT = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".aiff", ".ape",
}
VIDEO_EXT = {
    ".mp4", ".mkv", ".mov", ".avi", ".flv", ".wmv", ".webm", ".ts", ".m4v", ".mpg",
    ".mpeg", ".3gp", ".rmvb", ".rm", ".vob",
}
ALL_EXT = AUDIO_EXT | VIDEO_EXT


def is_supported(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in ALL_EXT

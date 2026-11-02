# -*- coding: utf-8 -*-
"""诊断：QVideoWidget 能不能出画面，以及样式表是否有影响。

分别用「不设样式表」和「套完整 QSS」两种方式播放同一个 mp4，
各抓一张整屏图，直接看图判断。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
VIDEO = os.path.join(ROOT, "testdata", "demo.mp4")
OUT = os.path.join(ROOT, "docs")


def run(with_qss: bool, tag: str) -> None:
    app = QApplication(sys.argv)
    if with_qss:
        from subtitle_forge.ui.styles import build_stylesheet

        app.setStyleSheet(build_stylesheet("light"))

    win = QWidget()
    win.resize(560, 360)
    lay = QVBoxLayout(win)
    lay.setContentsMargins(6, 6, 6, 6)
    vw = QVideoWidget()
    if with_qss:
        vw.setObjectName("VideoStage")     # 会命中 QSS 里的背景/圆角规则
    lay.addWidget(vw)
    win.setWindowTitle(tag)
    win.show()

    player = QMediaPlayer(win)
    audio = QAudioOutput(win)
    player.setAudioOutput(audio)
    player.setVideoOutput(vw)
    player.setSource(QUrl.fromLocalFile(VIDEO))

    # 直接抓解码出来的帧，绕开「窗口没在最前面 / 硬件叠加抓不到」的干扰
    saved = {"done": False}

    def on_frame(frame) -> None:
        if saved["done"] or not frame.isValid():
            return
        img = frame.toImage()
        if img.isNull():
            return
        img.save(os.path.join(OUT, f"diag-{tag}-frame.png"))
        saved["done"] = True
        print(f"{tag}: frame {img.width()}x{img.height()} saved")

    sink = player.videoSink()
    if sink is not None:
        sink.videoFrameChanged.connect(on_frame)
    player.play()

    def grab() -> None:
        scr = app.primaryScreen()
        if scr is not None:
            scr.grabWindow(int(win.winId())).save(os.path.join(OUT, f"diag-{tag}.png"))
        print(f"{tag}: hasVideo={player.hasVideo()} status={player.mediaStatus()} "
              f"pos={player.position()} frame_ok={saved['done']} err={player.errorString()!r}")
        player.stop()
        app.quit()

    QTimer.singleShot(2600, grab)
    app.exec()


if __name__ == "__main__":
    # QApplication 只能建一个，所以两种模式分成两次进程跑
    mode = sys.argv[1] if len(sys.argv) > 1 else "plain"
    run(mode == "styled", mode)

# -*- coding: utf-8 -*-
"""生成界面截图：浅色 / 深色 / 视频预览联动。

用真实窗口跑（不要 offscreen），否则 QVideoWidget 出不来画面。
    .venv\\Scripts\\python.exe tools\\shot_v2.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from subtitle_forge.core.models import Cue
from subtitle_forge.ui.main_window import MainWindow
from subtitle_forge.ui.styles import build_stylesheet

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DOCS = os.path.join(ROOT, "docs")

CUE_A = [
    (0, "大家好，今天聊聊本地字幕工具。"),
    (2400, "它完全离线运行，不联网。"),
    (5200, "导出的是 SRT 和纯文本两种格式。"),
]
CUE_B = [
    (0, "The tribal chieftain called for the boy."),
    (3600, "And presented him with 50 pieces of gold."),
]


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(build_stylesheet("light"))
    win = MainWindow()
    # 截图要可复现：不受上次保存的主题影响
    win.theme = "light"
    win._apply_theme()
    win.show()

    video = os.path.join(ROOT, "testdata", "demo.mp4")
    audio = os.path.join(ROOT, "testdata", "zh.wav")
    en = os.path.join(ROOT, "testdata", "en.wav")
    files = [p for p in (video, audio, en) if os.path.isfile(p)]
    win._add_files(files)

    def fake_cues() -> None:
        for i, rows in ((0, CUE_A), (1, CUE_B)):
            if i >= len(win.docs):
                continue
            doc = win.docs[i]
            doc.cues = [
                Cue(n + 1, s, s + 2000, t) for n, (s, t) in enumerate(rows)
            ]
            doc.status = f"完成 {len(doc.cues)} 条"
            doc.view.set_cues(doc.cues)
        win._refresh_file_list()
        win.tabs.setCurrentIndex(0)
        win._activate(win.docs[0])
        # 跳到第 2 句，验证「点字幕 → 视频跟随」
        if win.docs[0].cues:
            win._on_row_play(1)

    QTimer.singleShot(700, fake_cues)

    def shot_light() -> None:
        win.grab().save(os.path.join(DOCS, "ui2-light.png"))
        p = win.preview._player
        if p is not None:
            print(
                "player: hasVideo=", p.hasVideo(),
                "| status=", p.mediaStatus(),
                "| error=", repr(p.errorString()),
                "| pos=", p.position(),
                "| dur=", p.duration(),
            )
        # QVideoWidget 走的是独立原生表面，win.grab() 抓不到画面，
        # 这里再抓一次整屏，用来确认视频真的在解码
        from PySide6.QtWidgets import QApplication as _App

        scr = _App.primaryScreen()
        if scr is not None:
            scr.grabWindow(0).save(os.path.join(DOCS, "ui2-screen.png"))
            print("saved ui2-screen.png")
        print("saved ui2-light.png")

    def to_dark() -> None:
        win._toggle_theme()
        win.params.set_expanded(True)

    def shot_dark() -> None:
        win.grab().save(os.path.join(DOCS, "ui2-dark.png"))
        print("saved ui2-dark.png", "| theme=", win.theme)

    def done() -> None:
        win.preview.pause()
        app.quit()

    QTimer.singleShot(3200, shot_light)
    QTimer.singleShot(3400, to_dark)
    QTimer.singleShot(4200, shot_dark)
    QTimer.singleShot(4600, done)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""端到端验证：一次导入多个文件、连续转写，确认各自结果互不覆盖。

    .venv\\Scripts\\python.exe tools\\test_queue.py
需要 models/sensevoice/ 已放好模型，且 testdata 里有 zh.wav / en.wav。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from subtitle_forge.ui.main_window import MainWindow
from subtitle_forge.ui.styles import build_stylesheet

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FILES = [
    os.path.join(ROOT, "testdata", "zh.wav"),
    os.path.join(ROOT, "testdata", "en.wav"),
]


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(build_stylesheet("light"))
    win = MainWindow()
    win.show()

    win._add_files([p for p in FILES if os.path.isfile(p)])
    print(f"导入 {len(win.docs)} 个文件，标签页 {win.tabs.count()} 个")

    QTimer.singleShot(300, win._start)

    state = {"ticks": 0}

    def check() -> None:
        state["ticks"] += 1
        busy = win._worker is not None and win._worker.isRunning()
        if busy and state["ticks"] < 240:
            return
        timer.stop()
        ok = True
        for d in win.docs:
            rows = d.view.table.rowCount() if d.view else 0
            first = d.view.table.item(0, 4).text() if rows else ""
            print(f"- {d.name}: status={d.status} 行数={rows} 首行={first!r}")
            ok = ok and rows > 0 and rows == len(d.cues)
        if len(win.docs) >= 2:
            a = win.docs[0].view.table.item(0, 4).text()
            b = win.docs[1].view.table.item(0, 4).text()
            print(f"两份内容不同: {a != b}")
            ok = ok and a != b
        win.grab().save(os.path.join(ROOT, "docs", "ui2-queue.png"))
        print("QUEUE OK" if ok else "QUEUE FAILED")
        app.quit()

    timer = QTimer()
    timer.setInterval(500)
    timer.timeout.connect(check)
    timer.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

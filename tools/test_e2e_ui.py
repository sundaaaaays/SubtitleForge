# -*- coding: utf-8 -*-
"""UI 端到端测试：模拟真实点击流程，验证从导入到导出的全链路。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from subtitle_forge.ui.main_window import MainWindow
from subtitle_forge.ui.styles import build_stylesheet

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WAV = os.path.join(ROOT, "testdata", "zh.wav")

app = QApplication(sys.argv)
app.setStyleSheet(build_stylesheet())

win = MainWindow()
win.resize(1180, 760)
win.show()

from subtitle_forge.audio.decoder import find_ffmpeg
print("[0] ffmpeg:", find_ffmpeg())
win._add_files([WAV])
print(f"[1] 已添加到列表：{win.file_list.count()} 个")

state = {"ticks": 0, "done": False}


def tick():
    state["ticks"] += 1
    if win._worker is None:
        if state["ticks"] > 300:
            print("[!] 超时：worker 未创建")
            app.quit()
        return
    if win._worker.isRunning():
        return
    if not state["done"]:
        # 转写已经结束（成功或失败）
        state["done"] = True
        print(f"[3] 转写结束，字幕 {len(win._cues)} 条，表格 {win.table.rowCount()} 行")
        for i, c in enumerate(win._cues):
            print(f"      [{i+1}] {c.start_ms:>6} - {c.end_ms:>6}  {c.text}")

        # 导出
        out = tempfile.mkdtemp(prefix="sf_export_")
        from subtitle_forge.core import exporters
        from subtitle_forge.core.models import ExportOptions

        opt = ExportOptions(formats=["srt", "txt"], with_timestamp=True)
        written = exporters.export(win._cues, opt, WAV, out)
        print(f"[4] 导出 {len(written)} 个文件到 {out}")
        for p in written:
            print(f"      - {os.path.basename(p)}  ({os.path.getsize(p)} 字节)")
            with open(p, encoding="utf-8-sig") as f:
                content = f.read()
            print("        " + content.replace("\r\n", "\n").replace("\n", "\n        ").rstrip())

        # 截图（完成态）
        shot = os.path.join(ROOT, "docs", "ui-result.png")
        win.grab().save(shot)
        print(f"[5] 截图：{shot}")
        app.quit()
        return

    if state["ticks"] > 300:      # 30 秒超时
        print("[!] 超时")
        app.quit()


timer = QTimer()
timer.timeout.connect(tick)
timer.start(100)


def kickoff():
    print("[2] 点击开始转写…")
    win._start()


QTimer.singleShot(300, kickoff)
sys.exit(app.exec())

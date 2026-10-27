# -*- coding: utf-8 -*-
"""启动窗口、填入示例数据、截图，用于检查界面渲染。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from subtitle_forge.core.models import Cue
from subtitle_forge.ui.main_window import MainWindow
from subtitle_forge.ui.styles import build_stylesheet

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

SAMPLE = [
    (0, 1240, "大家好，今天我们聊一下离线语音识别。"),
    (1320, 5180, "首先看需求：完全在本地运行，不联网，"),
    (5240, 8460, "也不能有账号体系，这是第一点。"),
    (8520, 11900, "第二点是速度，一小时音频要在十分钟内处理完，"),
    (11960, 14300, "否则用户体验会很差。"),
    (14360, 17800, "第三点是断句质量，字幕读起来要顺。"),
]

app = QApplication(sys.argv)
app.setStyleSheet(build_stylesheet())

win = MainWindow()
win.resize(1180, 760)
win.show()

# 填假数据，只为看排版
win._files = [
    {"path": os.path.join(ROOT, "testdata", "zh.wav"), "duration": 5.6, "status": "完成 1 条"},
    {"path": os.path.join(ROOT, "testdata", "en.wav"), "duration": 7.2, "status": "完成 3 条"},
]
win._refresh_file_list()
win.file_list.setCurrentRow(0)

win._cues = [Cue(i + 1, s, e, t) for i, (s, e, t) in enumerate(SAMPLE)]
win._fill_table()

win.progress.setValue(1000)
win._set_progress_state("done")
win.lbl_stage.setText("完成：6 条字幕，用时 4.2s（约 12.4× 实时）")
win.lbl_stat.setText("6 条 · 0:17 · sherpa-onnx / SenseVoice")
win.btn_export.setEnabled(True)
win._status("转写完成")


def shoot():
    out_dir = os.path.join(ROOT, "docs")
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "ui-main.png")
    win.grab().save(p)
    print("saved:", p)
    app.quit()


QTimer.singleShot(900, shoot)
sys.exit(app.exec())

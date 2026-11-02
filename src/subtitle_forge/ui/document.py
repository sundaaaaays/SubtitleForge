# -*- coding: utf-8 -*-
"""每个音视频文件对应一份 Document，各自持有独立的字幕表格。

之前所有文件共用一张表，第二个文件识别完就把第一个覆盖了。现在拆成
「一个文件 → 一个 Document → 一个 DocView」，界面上用标签页分开。
"""
from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QStackedLayout,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..audio.decoder import VIDEO_EXT
from ..core.models import Cue
from ..core.textutil import ms_to_srt, parse_timecode

COLUMNS = ["#", "开始", "结束", "时长", "文本"]


class DocView(QWidget):
    """单个文件的字幕表格。没结果时显示空态提示。"""

    playRequested = Signal(int)   # 请求播放第 N 行
    changed = Signal()            # 字幕被手工修改

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cues: List[Cue] = []

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked
        )
        hh = self.table.horizontalHeader()
        for c in range(4):
            hh.setSectionResizeMode(c, QHeaderView.Fixed)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 46)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 66)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.cellClicked.connect(self._on_cell_clicked)

        self.hint = QLabel("还没有转写结果。\n点左侧「开始转写」即可。")
        self.hint.setObjectName("EmptyHint")
        self.hint.setAlignment(Qt.AlignCenter)

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self.hint)
        self._stack.addWidget(self.table)
        self._stack.setCurrentIndex(0)

    # ---------------------------------------------------------------- 数据

    def set_cues(self, cues: List[Cue]) -> None:
        self.cues = list(cues)
        self._fill()
        self._stack.setCurrentIndex(1 if self.cues else 0)

    def set_hint(self, text: str) -> None:
        self.hint.setText(text)

    def current_row(self) -> int:
        return self.table.currentRow()

    def highlight_row(self, row: int) -> None:
        """播放时把当前行标出来并滚动到可见位置。"""
        if not (0 <= row < self.table.rowCount()):
            return
        if self.table.currentRow() == row:
            return
        self.table.blockSignals(True)
        self.table.selectRow(row)
        self.table.blockSignals(False)
        self.table.scrollToItem(self.table.item(row, 0))

    def _fill(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.cues))
        for r, cue in enumerate(self.cues):
            self._set_row(r, cue)
        self.table.blockSignals(False)

    def _set_row(self, r: int, c: Cue) -> None:
        items = [
            QTableWidgetItem(str(r + 1)),
            QTableWidgetItem(ms_to_srt(c.start_ms)),
            QTableWidgetItem(ms_to_srt(c.end_ms)),
            QTableWidgetItem(f"{c.duration_ms / 1000:.2f}s"),
            QTableWidgetItem(c.text),
        ]
        items[0].setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        items[3].setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        items[0].setTextAlignment(Qt.AlignCenter)
        items[3].setTextAlignment(Qt.AlignCenter)
        for col, it in enumerate(items):
            self.table.setItem(r, col, it)

    # ---------------------------------------------------------------- 编辑

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        r, col = item.row(), item.column()
        if not (0 <= r < len(self.cues)):
            return
        cue = self.cues[r]
        text = item.text()

        if col == 4:
            if not text.strip():
                return
            self.cues[r] = Cue(cue.index, cue.start_ms, cue.end_ms, text)
        elif col in (1, 2):
            ms = parse_timecode(text)
            if ms < 0:
                self.table.blockSignals(True)
                self.table.setItem(
                    r, col,
                    QTableWidgetItem(ms_to_srt(cue.start_ms if col == 1 else cue.end_ms)),
                )
                self.table.blockSignals(False)
                return
            if col == 1:
                self.cues[r] = Cue(cue.index, ms, max(ms + 300, cue.end_ms), cue.text)
            else:
                self.cues[r] = Cue(cue.index, cue.start_ms, max(cue.start_ms + 300, ms), cue.text)
        else:
            return

        self.table.blockSignals(True)
        self._set_row(r, self.cues[r])
        self.table.blockSignals(False)
        self.changed.emit()

    def _on_cell_clicked(self, row: int, col: int) -> None:
        if col == 4:      # 点文本列是要编辑，别抢着播放
            return
        self.playRequested.emit(row)


class Document:
    """一个待转写文件的全部状态。"""

    def __init__(self, path: str) -> None:
        self.path = path
        self.name = os.path.basename(path)
        self.duration = 0.0
        self.status = "待处理"
        self.result = None
        self.wav_path = ""
        self.cues: List[Cue] = []
        self.view: Optional[DocView] = None
        self.dirty = False

    @property
    def is_video(self) -> bool:
        return os.path.splitext(self.path)[1].lower() in VIDEO_EXT

    @property
    def done(self) -> bool:
        return bool(self.cues)

    def media_source(self) -> str:
        """预览播放用哪个文件：优先原始视频（要出画面），否则用解码出的 wav。"""
        if self.is_video and os.path.isfile(self.path):
            return self.path
        if self.wav_path and os.path.isfile(self.wav_path):
            return self.wav_path
        return self.path

# -*- coding: utf-8 -*-
"""主窗口。"""
from __future__ import annotations

import os
import sys
import traceback
from typing import List, Optional

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..audio.decoder import ALL_EXT, find_ffmpeg, probe
from ..core import exporters
from ..core.models import Cue, ExportOptions, SplitOptions
from ..core.pipeline import TranscribeConfig
from ..core.textutil import ms_to_srt, parse_timecode, visual_width
from .styles import COLORS, QSS
from .worker import TranscribeWorker

APP_TITLE = "字幕工坊 SubtitleForge"

LANG_ITEMS = [
    ("自动检测", "auto"),
    ("中文（普通话）", "zh"),
    ("英文", "en"),
    ("中英混合", "auto"),
    ("日语", "ja"),
    ("韩语", "ko"),
    ("粤语", "yue"),
]

ENV_ITEMS = [
    ("安静室内（默认）", "quiet"),
    ("会议 / 访谈", "meeting"),
    ("嘈杂户外", "outdoor"),
    ("快速对话", "dialogue"),
    ("课堂 / 讲座", "lecture"),
]

ENC_ITEMS = [
    ("UTF-8（带 BOM，推荐）", "utf-8-sig"),
    ("UTF-8（无 BOM）", "utf-8"),
    ("GBK（兼容老播放器）", "gb18030"),
    ("UTF-16 LE", "utf-16"),
]

TXT_LAYOUT_ITEMS = [
    ("每句一行", "line"),
    ("连续整段", "continuous"),
    ("按段落合并", "paragraph"),
]


def app_root() -> str:
    """程序根目录。打包后是 exe 所在目录，开发时是项目根。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def model_candidates() -> list[str]:
    """模型可能所在的目录，按优先级排列。

    正常布局是 <根>/models/sensevoice/；但也兼容把 onnx 直接放在 models/ 下，
    以及 PyInstaller 把 datas 塞进 _internal/ 的情况。
    """
    roots = [app_root()]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(meipass)
    dirs: list[str] = []
    for r in roots:
        dirs.append(os.path.join(r, "models", "sensevoice"))
        dirs.append(os.path.join(r, "models"))
    return dirs


def resolve_model():
    """定位模型。返回 (kind, kwargs)；找不到时返回 ('demo', {}) 走演示引擎。"""
    for d in model_candidates():
        model = os.path.join(d, "model.int8.onnx")
        tokens = os.path.join(d, "tokens.txt")
        if os.path.isfile(model) and os.path.isfile(tokens):
            return "sensevoice", {"model_path": model, "tokens_path": tokens}
    return "demo", {}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1180, 760)
        self.setMinimumSize(940, 620)

        self._files: List[dict] = []
        self._cues: List[Cue] = []
        self._result = None
        self._engine = None
        self._worker: Optional[TranscribeWorker] = None
        self._playing_row = -1
        self._stop_at_ms = -1
        self._dirty = False

        self._build_ui()
        self._build_player()
        self._build_shortcuts()
        self._refresh_model_badge()
        self.setAcceptDrops(True)

    # ================================================================ UI 构建

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(14, 12, 14, 8)
        body_layout.setSpacing(12)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([330, 830])

        body_layout.addWidget(splitter)
        root.addWidget(body, 1)
        root.addWidget(self._build_footer())

        self.setCentralWidget(central)
        self._build_statusbar()

    def _build_header(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("HeaderBar")
        bar.setFixedHeight(62)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 0, 18, 0)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        t = QLabel(APP_TITLE)
        t.setObjectName("HeaderTitle")
        s = QLabel("本地离线音视频转字幕 · 导出 SRT / TXT")
        s.setObjectName("HeaderSub")
        titles.addWidget(t)
        titles.addWidget(s)
        lay.addLayout(titles)
        lay.addStretch(1)

        self.badge_model = QLabel("模型检测中…")
        self.badge_model.setObjectName("Hint")
        lay.addWidget(self.badge_model)

        btn_open_dir = QPushButton("模型目录")
        btn_open_dir.setToolTip("打开模型所在目录")
        btn_open_dir.clicked.connect(self._open_model_dir)
        lay.addWidget(btn_open_dir)

        return bar

    def _build_left(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(310)
        panel.setMaximumWidth(400)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # ---- 文件列表 ----
        card1 = self._card()
        c1 = QVBoxLayout(card1)
        c1.setContentsMargins(12, 10, 12, 10)
        c1.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("待转写文件")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.lbl_count = QLabel("0 个")
        self.lbl_count.setObjectName("Hint")
        head.addWidget(self.lbl_count)
        c1.addLayout(head)

        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(120)
        self.file_list.currentRowChanged.connect(self._on_file_selected)
        c1.addWidget(self.file_list, 1)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_add = QPushButton("添加文件")
        self.btn_add.clicked.connect(self._pick_files)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.clicked.connect(self._clear_files)
        row.addWidget(self.btn_add, 1)
        row.addWidget(self.btn_clear)
        c1.addLayout(row)
        lay.addWidget(card1, 1)

        # ---- 参数 ----
        card2 = self._card()
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(12, 10, 12, 12)
        c2.setSpacing(9)

        t2 = QLabel("识别参数")
        t2.setObjectName("CardTitle")
        c2.addWidget(t2)

        self.cmb_lang = QComboBox()
        for label, _ in LANG_ITEMS:
            self.cmb_lang.addItem(label)
        c2.addLayout(self._field("语言", self.cmb_lang))

        self.cmb_env = QComboBox()
        for label, _ in ENV_ITEMS:
            self.cmb_env.addItem(label)
        c2.addLayout(self._field("环境", self.cmb_env))

        self.spin_chars = QSpinBox()
        self.spin_chars.setRange(6, 40)
        self.spin_chars.setValue(18)
        self.spin_chars.setSuffix(" 字")
        c2.addLayout(self._field("单条字数", self.spin_chars))

        self.spin_dur = QDoubleSpinBox()
        self.spin_dur.setRange(1.5, 15.0)
        self.spin_dur.setSingleStep(0.5)
        self.spin_dur.setValue(6.0)
        self.spin_dur.setSuffix(" 秒")
        c2.addLayout(self._field("单条时长", self.spin_dur))

        self.spin_gap = QDoubleSpinBox()
        self.spin_gap.setRange(0.2, 3.0)
        self.spin_gap.setSingleStep(0.1)
        self.spin_gap.setValue(0.6)
        self.spin_gap.setSuffix(" 秒")
        c2.addLayout(self._field("静音断句", self.spin_gap))

        lay.addWidget(card2)

        # ---- 操作按钮 ----
        self.btn_start = QPushButton("开始转写")
        self.btn_start.setObjectName("Primary")
        self.btn_start.setMinimumHeight(38)
        self.btn_start.clicked.connect(self._start)
        lay.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("Danger")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        lay.addWidget(self.btn_cancel)
        lay.addSpacing(4)

        return panel

    def _build_right(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # ---- 进度 ----
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        lay.addWidget(self.progress)

        self.lbl_stage = QLabel("就绪。把音视频文件拖进窗口，或点「添加文件」。")
        self.lbl_stage.setObjectName("Hint")
        lay.addWidget(self.lbl_stage)

        # ---- 表格 ----
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "开始", "结束", "时长", "文本"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked
        )
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.Fixed)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 46)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 66)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.cellClicked.connect(self._on_cell_clicked)
        lay.addWidget(self.table, 1)

        # ---- 播放条 ----
        play_row = QHBoxLayout()
        play_row.setSpacing(8)
        self.btn_play = QPushButton("▶ 播放选中")
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_play.setEnabled(False)
        play_row.addWidget(self.btn_play)

        self.lbl_pos = QLabel("00:00:00,000")
        self.lbl_pos.setObjectName("Hint")
        play_row.addWidget(self.lbl_pos)
        play_row.addStretch(1)

        self.lbl_stat = QLabel("—")
        self.lbl_stat.setObjectName("Hint")
        play_row.addWidget(self.lbl_stat)
        lay.addLayout(play_row)

        # ---- 导出区 ----
        card = self._card()
        exp = QHBoxLayout(card)
        exp.setContentsMargins(12, 9, 12, 9)
        exp.setSpacing(10)

        t = QLabel("导出")
        t.setObjectName("CardTitle")
        exp.addWidget(t)

        self.chk_srt = QCheckBox("SRT")
        self.chk_srt.setChecked(True)
        exp.addWidget(self.chk_srt)
        self.chk_txt = QCheckBox("TXT")
        self.chk_txt.setChecked(True)
        exp.addWidget(self.chk_txt)
        self.chk_vtt = QCheckBox("VTT")
        exp.addWidget(self.chk_vtt)

        exp.addWidget(self._vline())

        self.cmb_txtlayout = QComboBox()
        for label, _ in TXT_LAYOUT_ITEMS:
            self.cmb_txtlayout.addItem(label)
        self.cmb_txtlayout.setFixedWidth(112)
        self.cmb_txtlayout.setToolTip("TXT 排版方式")
        exp.addWidget(self.cmb_txtlayout)

        self.chk_tstamp = QCheckBox("带时间戳")
        self.chk_tstamp.setToolTip("在 TXT 每行前加 [mm:ss]")
        exp.addWidget(self.chk_tstamp)

        self.chk_punct = QCheckBox("保留标点")
        self.chk_punct.setChecked(True)
        exp.addWidget(self.chk_punct)

        self.cmb_enc = QComboBox()
        for label, _ in ENC_ITEMS:
            self.cmb_enc.addItem(label)
        self.cmb_enc.setFixedWidth(212)
        exp.addWidget(self.cmb_enc)

        exp.addStretch(1)

        self.btn_export = QPushButton("导出…")
        self.btn_export.setObjectName("Primary")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export)
        exp.addWidget(self.btn_export)

        lay.addWidget(card)
        return panel

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(0)
        return w

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.lbl_sb_left = QLabel("就绪")
        sb.addWidget(self.lbl_sb_left)
        self.lbl_sb_right = QLabel("")
        sb.addPermanentWidget(self.lbl_sb_right)

    # ---------------------------------------------------------------- 小工具

    def _card(self) -> QFrame:
        f = QFrame()
        f.setObjectName("Card")
        return f

    def _vline(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.VLine)
        f.setStyleSheet("color: #e4e4e0;")
        f.setFixedWidth(1)
        return f

    def _field(self, label: str, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        lb = QLabel(label)
        lb.setFixedWidth(62)
        lb.setObjectName("Hint")
        row.addWidget(lb)
        row.addWidget(widget, 1)
        return row

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence.Open, self, self._pick_files)
        QShortcut(QKeySequence("Ctrl+R"), self, self._start)
        QShortcut(QKeySequence("Ctrl+E"), self, self._export)

    # ================================================================ 播放

    def _build_player(self) -> None:
        self._player = None
        self._audio = None
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._audio.setVolume(0.85)
            self._player.setAudioOutput(self._audio)
            self._timer = QTimer(self)
            self._timer.setInterval(80)
            self._timer.timeout.connect(self._on_play_tick)
        except Exception:
            self._player = None

    def _load_media(self, wav_path: str) -> None:
        if self._player is None:
            return
        if not wav_path or not os.path.isfile(wav_path):
            return
        from PySide6.QtMultimedia import QMediaPlayer

        self._player.setSource(QUrl.fromLocalFile(wav_path))
        self._player.setPlaybackRate(1.0)
        _ = QMediaPlayer

    def _toggle_play(self) -> None:
        if self._player is None or self._result is None:
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self._cues):
            return
        self._play_row(row)

    def _play_row(self, row: int) -> None:
        if self._player is None or not self._cues:
            return
        cue = self._cues[row]
        self._playing_row = row
        self._stop_at_ms = cue.end_ms
        self._player.setPosition(max(0, cue.start_ms - 150))
        self._player.play()
        self._timer.start()
        self.btn_play.setText("■ 停止")

    def _on_play_tick(self) -> None:
        if self._player is None:
            return
        pos = self._player.position()
        self.lbl_pos.setText(ms_to_srt(pos))
        if self._stop_at_ms > 0 and pos >= self._stop_at_ms:
            self._player.pause()
            self._timer.stop()
            self.btn_play.setText("▶ 播放选中")

    # ================================================================ 文件

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = []
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.isfile(p) and os.path.splitext(p)[1].lower() in ALL_EXT:
                paths.append(p)
        if paths:
            self._add_files(paths)
        else:
            self._status("拖入的文件格式不支持")

    def _pick_files(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(ALL_EXT))
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择音视频文件", "", f"音视频文件 ({exts});;所有文件 (*.*)"
        )
        if files:
            self._add_files(files)

    def _add_files(self, paths: List[str]) -> None:
        added = 0
        for p in paths:
            if any(f["path"] == p for f in self._files):
                continue
            item = {"path": p, "duration": 0.0, "status": "待处理"}
            self._files.append(item)
            added += 1
        if added:
            self._refresh_file_list()
            self._status(f"已添加 {added} 个文件")
            if self.file_list.currentRow() < 0:
                self.file_list.setCurrentRow(0)
            self._probe_current()

    def _clear_files(self) -> None:
        if not self._files:
            return
        self._files.clear()
        self._refresh_file_list()
        self.table.setRowCount(0)
        self._cues = []
        self.btn_export.setEnabled(False)
        self.lbl_stat.setText("—")
        self._status("已清空")

    def _refresh_file_list(self) -> None:
        self.file_list.blockSignals(True)
        cur = self.file_list.currentRow()
        self.file_list.clear()
        for f in self._files:
            name = os.path.basename(f["path"])
            dur = self._fmt_dur(f["duration"])
            it = QListWidgetItem(f"{name}\n{dur}  ·  {f['status']}")
            it.setToolTip(f["path"])
            self.file_list.addItem(it)
        if 0 <= cur < self.file_list.count():
            self.file_list.setCurrentRow(cur)
        self.file_list.blockSignals(False)
        self.lbl_count.setText(f"{len(self._files)} 个")

    @staticmethod
    def _fmt_dur(sec: float) -> str:
        if sec <= 0:
            return "时长未知"
        m, s = divmod(int(sec), 60)
        h, m = divmod(m, 60)
        return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"

    def _on_file_selected(self, row: int) -> None:
        if 0 <= row < len(self._files):
            self._probe_current()

    def _probe_current(self) -> None:
        row = self.file_list.currentRow()
        if not (0 <= row < len(self._files)):
            return
        f = self._files[row]
        if f["duration"] > 0:
            return
        try:
            info = probe(f["path"])
            f["duration"] = info.duration_sec
            f["status"] = "待处理" if info.has_audio else "无音轨"
            self._refresh_file_list()
        except Exception as exc:
            f["status"] = "读取失败"
            self._refresh_file_list()
            self._status(f"读取失败：{exc}")

    # ================================================================ 转写

    def _ensure_engine(self):
        if self._engine is not None and getattr(self._engine, "ready", False):
            return self._engine

        kind, kw = resolve_model()
        if kind == "sensevoice":
            from ..asr.sensevoice import SenseVoiceEngine

            lang = LANG_ITEMS[self.cmb_lang.currentIndex()][1]
            self._engine = SenseVoiceEngine(
                kw["model_path"], kw["tokens_path"], language=lang,
                num_threads=max(2, min(8, (os.cpu_count() or 4) - 1)),
            )
        else:
            from ..core.pipeline import DemoEngine

            self._engine = DemoEngine()
        return self._engine

    def _start(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        row = self.file_list.currentRow()
        if not (0 <= row < len(self._files)):
            QMessageBox.information(self, "提示", "请先添加并选择一个文件。")
            return

        f = self._files[row]
        try:
            find_ffmpeg()
        except Exception as exc:
            QMessageBox.critical(self, "缺少 ffmpeg", str(exc))
            return

        split = SplitOptions(
            max_chars=self.spin_chars.value(),
            max_duration_sec=self.spin_dur.value(),
            silence_gap_sec=self.spin_gap.value(),
        )
        cfg = TranscribeConfig(
            language=LANG_ITEMS[self.cmb_lang.currentIndex()][1],
            environment=ENV_ITEMS[self.cmb_env.currentIndex()][1],
            split=split,
        )

        self._set_busy(True)
        f["status"] = "转写中"
        self._refresh_file_list()
        self.progress.setValue(0)
        self._set_progress_state(None)
        self._status(f"开始转写：{os.path.basename(f['path'])}")

        engine = self._ensure_engine()
        self._worker = TranscribeWorker(engine, f["path"], cfg, parent=self)
        self._worker.progressed.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_fail)
        self._worker.cancelled.connect(self._on_cancel)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.request_cancel()
            self._status("正在取消…")

    def _set_busy(self, busy: bool) -> None:
        self.btn_start.setEnabled(not busy)
        self.btn_add.setEnabled(not busy)
        self.btn_clear.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)
        self.cmb_lang.setEnabled(not busy)
        self.cmb_env.setEnabled(not busy)

    STAGE_TEXT = {
        "decode": "解码音频",
        "vad": "检测语音区间",
        "asr": "语音识别",
        "split": "断句与对齐",
    }

    def _set_progress_state(self, state: str | None) -> None:
        """切换进度条配色：进行中红、完成绿、失败红。"""
        self.progress.setProperty("done", state == "done")
        self.progress.setProperty("failed", state == "failed")
        self.progress.style().unpolish(self.progress)
        self.progress.style().polish(self.progress)
        self.progress.update()

    def _on_progress(self, stage: str, ratio: float, message: str, cues: int) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, ratio)) * 1000))
        label = self.STAGE_TEXT.get(stage, stage)
        self.lbl_stage.setText(f"[{label}] {message}")
        if cues:
            self.lbl_stat.setText(f"已识别 {cues} 段")

    def _on_success(self, result) -> None:
        self._result = result
        self._cues = list(result.cues)
        self._fill_table()
        self._load_media(result.wav_path)
        self.btn_play.setEnabled(self._player is not None)
        self.btn_export.setEnabled(bool(self._cues))
        self._set_busy(False)
        self.progress.setValue(1000)
        self._set_progress_state("done")

        row = self.file_list.currentRow()
        if 0 <= row < len(self._files):
            self._files[row]["status"] = f"完成 {len(self._cues)} 条"
            self._refresh_file_list()

        speed = result.duration_sec / max(result.elapsed_sec, 1e-6)
        self.lbl_stage.setText(
            f"完成：{len(self._cues)} 条字幕，用时 {result.elapsed_sec:.1f}s（约 {speed:.1f}× 实时）"
        )
        self.lbl_stat.setText(
            f"{len(self._cues)} 条 · {self._fmt_dur(result.duration_sec)} · {result.model_name}"
        )
        self._status("转写完成")

    def _on_fail(self, message: str) -> None:
        self._set_busy(False)
        self.progress.setValue(1000)
        self._set_progress_state("failed")
        self.lbl_stage.setText("转写失败")
        row = self.file_list.currentRow()
        if 0 <= row < len(self._files):
            self._files[row]["status"] = "失败"
            self._refresh_file_list()
        self._status("转写失败")
        QMessageBox.critical(self, "转写失败", message)

    def _on_cancel(self) -> None:
        self._set_busy(False)
        self.progress.setValue(0)
        self._set_progress_state(None)
        self.lbl_stage.setText("已取消")
        row = self.file_list.currentRow()
        if 0 <= row < len(self._files):
            self._files[row]["status"] = "已取消"
            self._refresh_file_list()
        self._status("已取消")

    # ================================================================ 表格

    def _fill_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._cues))
        for r, c in enumerate(self._cues):
            self._set_row(r, c)
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

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        r, col = item.row(), item.column()
        if not (0 <= r < len(self._cues)):
            return
        cue = self._cues[r]
        text = item.text()

        if col == 4:
            if not text.strip():
                return
            self._cues[r] = Cue(cue.index, cue.start_ms, cue.end_ms, text)
            self._dirty = True
        elif col in (1, 2):
            ms = parse_timecode(text)
            if ms < 0:
                self.table.blockSignals(True)
                self.table.setItem(r, col, QTableWidgetItem(
                    ms_to_srt(cue.start_ms if col == 1 else cue.end_ms)))
                self.table.blockSignals(False)
                return
            if col == 1:
                self._cues[r] = Cue(cue.index, ms, max(ms + 300, cue.end_ms), cue.text)
            else:
                self._cues[r] = Cue(cue.index, cue.start_ms, max(cue.start_ms + 300, ms), cue.text)
            self._dirty = True
        else:
            return

        self.table.blockSignals(True)
        self._set_row(r, self._cues[r])
        self.table.blockSignals(False)

    def _on_cell_clicked(self, row: int, col: int) -> None:
        if col == 4 or self._player is None:
            return
        self._play_row(row)

    # ================================================================ 导出

    def _export(self) -> None:
        if not self._cues:
            return

        formats = []
        if self.chk_srt.isChecked():
            formats.append("srt")
        if self.chk_txt.isChecked():
            formats.append("txt")
        if self.chk_vtt.isChecked():
            formats.append("vtt")
        if not formats:
            QMessageBox.information(self, "提示", "请至少勾选一种导出格式。")
            return

        src = self._result.source_path if self._result else ""
        default_dir = os.path.dirname(src) if src else os.path.expanduser("~")
        out_dir = QFileDialog.getExistingDirectory(self, "选择导出目录", default_dir)
        if not out_dir:
            return

        opt = ExportOptions(
            formats=formats,
            encoding=ENC_ITEMS[self.cmb_enc.currentIndex()][1],
            txt_layout=TXT_LAYOUT_ITEMS[self.cmb_txtlayout.currentIndex()][1],
            with_timestamp=self.chk_tstamp.isChecked(),
            keep_punctuation=self.chk_punct.isChecked(),
        )

        problems = exporters.validate(self._cues)
        if problems:
            head = "\n".join(problems[:8])
            more = f"\n… 另有 {len(problems) - 8} 条问题" if len(problems) > 8 else ""
            ans = QMessageBox.question(
                self, "导出前检查",
                f"发现 {len(problems)} 处可能的问题：\n\n{head}{more}\n\n仍然导出吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if ans != QMessageBox.Yes:
                return

        try:
            written = exporters.export(self._cues, opt, src or "subtitle", out_dir)
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", f"{type(exc).__name__}: {exc}")
            return

        if not written:
            QMessageBox.warning(self, "导出结果为空", "没有生成任何文件。")
            return

        names = "\n".join(os.path.basename(p) for p in written)
        self._status(f"已导出 {len(written)} 个文件到 {out_dir}")
        QMessageBox.information(self, "导出完成", f"已生成：\n\n{names}\n\n目录：{out_dir}")

    # ================================================================ 杂项

    def _open_model_dir(self) -> None:
        path = os.path.join(app_root(), "models")
        os.makedirs(path, exist_ok=True)
        if os.name == "nt":
            os.startfile(path)  # noqa: S606

    def _refresh_model_badge(self) -> None:
        kind, _ = resolve_model()
        if kind == "sensevoice":
            self.badge_model.setText("● 模型已就绪 · SenseVoice")
            self.badge_model.setStyleSheet(f"color: {COLORS['ok']};")
        else:
            self.badge_model.setText("● 未找到模型 · 演示模式")
            self.badge_model.setStyleSheet(f"color: {COLORS['warn']};")
            self.badge_model.setToolTip(
                "把模型放到 models/sensevoice/ 目录后重启即可启用真实识别：\n"
                "model.int8.onnx + tokens.txt"
            )

    def _status(self, text: str) -> None:
        self.lbl_sb_left.setText(text)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker and self._worker.isRunning():
            ans = QMessageBox.question(
                self, "正在转写", "任务还在进行中，确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                event.ignore()
                return
            self._worker.request_cancel()
            self._worker.wait(3000)
        if self._result is not None:
            from ..core.pipeline import TranscriptionPipeline

            TranscriptionPipeline.cleanup(self._result.wav_path)
        event.accept()

# -*- coding: utf-8 -*-
"""主窗口。

界面分区：
  左  文件列表 / 视频预览 / 识别参数（可折叠） / 操作按钮
  右  进度 + 每个文件一个标签页的字幕表格 + 播放条 + 导出

多文件互不覆盖靠的是「一个文件一份 Document + 一个 DocView」，
标签页只是把它们摆出来。
"""
from __future__ import annotations

import os
import sys
from typing import List, Optional

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..audio.decoder import ALL_EXT, find_ffmpeg, probe
from ..core import exporters
from ..core.models import ExportOptions, SplitOptions
from ..core.pipeline import TranscribeConfig, TranscriptionPipeline
from ..core.textutil import ms_to_srt
from .. import __version__
from .document import Document, DocView
from .preview import PreviewPanel
from .styles import palette
from .worker import TranscribeWorker

APP_TITLE = "字幕工坊 SubtitleForge"
ORG = "SubtitleForge"
APP = "SubtitleForge"

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


class CollapsibleCard(QFrame):
    """带折叠头的卡片。收起后只留一条标题，省出空间给预览窗。"""

    toggled = Signal(bool)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._title = title
        self._expanded = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 10)
        outer.setSpacing(8)

        self.head = QPushButton()
        self.head.setObjectName("CollapseHead")
        self.head.setCursor(Qt.PointingHandCursor)
        self.head.clicked.connect(self.toggle)
        outer.addWidget(self.head)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(9)
        outer.addWidget(self.body)

        self._sync_text()

    def _sync_text(self) -> None:
        arrow = "▾" if self._expanded else "▸"
        self.head.setText(f"{arrow}  {self._title}")

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, on: bool) -> None:
        self._expanded = on
        self.body.setVisible(on)
        self._sync_text()
        self.toggled.emit(on)

    def add_layout(self, lay) -> None:
        self.body_layout.addLayout(lay)

    def add_widget(self, w: QWidget) -> None:
        self.body_layout.addWidget(w)

    @property
    def expanded(self) -> bool:
        return self._expanded


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1240, 800)
        self.setMinimumSize(1080, 680)

        self.docs: List[Document] = []
        self.current: Optional[Document] = None
        self._engine = None
        self._worker: Optional[TranscribeWorker] = None
        self._worker_doc: Optional[Document] = None
        self._queue: List[Document] = []
        self._batch_total = 0
        self._batch_done = 0
        self._batch_failed = 0
        self._syncing = False

        self.settings = QSettings(ORG, APP)
        self.theme = self.settings.value("theme", "light")

        self._build_ui()
        self._build_shortcuts()
        self._refresh_model_badge()
        self._apply_theme()
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
        splitter.setSizes([352, 860])

        body_layout.addWidget(splitter)
        root.addWidget(body, 1)

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
        s = QLabel(f"本地离线音视频转字幕 · 导出 SRT / TXT · v{__version__}")
        s.setObjectName("HeaderSub")
        titles.addWidget(t)
        titles.addWidget(s)
        lay.addLayout(titles)
        lay.addStretch(1)

        self.badge_model = QLabel("模型检测中…")
        self.badge_model.setObjectName("Hint")
        lay.addWidget(self.badge_model)

        self.btn_theme = QPushButton("夜间模式")
        self.btn_theme.setObjectName("Ghost")
        self.btn_theme.setToolTip("切换深色 / 浅色外观（Ctrl+D）")
        self.btn_theme.clicked.connect(self._toggle_theme)
        lay.addWidget(self.btn_theme)

        btn_open_dir = QPushButton("模型目录")
        btn_open_dir.clicked.connect(self._open_model_dir)
        lay.addWidget(btn_open_dir)

        return bar

    def _build_left(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(330)
        panel.setMaximumWidth(440)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

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
        self.file_list.setMinimumHeight(86)
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

        # ---- 视频预览（左侧中间） ----
        card_prev = self._card()
        cp = QVBoxLayout(card_prev)
        cp.setContentsMargins(10, 8, 10, 10)
        cp.setSpacing(6)

        ph = QHBoxLayout()
        t_prev = QLabel("视频预览")
        t_prev.setObjectName("CardTitle")
        ph.addWidget(t_prev)
        ph.addStretch(1)
        self.btn_play_prev = QPushButton("▶ 播放")
        self.btn_play_prev.setObjectName("Ghost")
        self.btn_play_prev.clicked.connect(self._toggle_play)
        ph.addWidget(self.btn_play_prev)
        cp.addLayout(ph)

        self.preview = PreviewPanel()
        self.preview.setFixedHeight(168)
        self.preview.positionChanged.connect(self._on_preview_pos)
        self.preview.playingChanged.connect(self._on_playing_changed)
        cp.addWidget(self.preview)
        lay.addWidget(card_prev)

        # ---- 识别参数（可折叠） ----
        self.params = CollapsibleCard("识别参数")
        self.params.set_expanded(False)
        self.params.toggled.connect(self._on_params_toggled)

        self.cmb_lang = QComboBox()
        for label, _ in LANG_ITEMS:
            self.cmb_lang.addItem(label)
        self.params.add_layout(self._field("语言", self.cmb_lang))

        self.cmb_env = QComboBox()
        for label, _ in ENV_ITEMS:
            self.cmb_env.addItem(label)
        self.params.add_layout(self._field("环境", self.cmb_env))

        self.spin_chars = QSpinBox()
        self.spin_chars.setRange(6, 40)
        self.spin_chars.setValue(18)
        self.spin_chars.setSuffix(" 字")
        self.params.add_layout(self._field("单条字数", self.spin_chars))

        self.spin_dur = QDoubleSpinBox()
        self.spin_dur.setRange(1.5, 15.0)
        self.spin_dur.setSingleStep(0.5)
        self.spin_dur.setValue(6.0)
        self.spin_dur.setSuffix(" 秒")
        self.params.add_layout(self._field("单条时长", self.spin_dur))

        self.spin_gap = QDoubleSpinBox()
        self.spin_gap.setRange(0.2, 3.0)
        self.spin_gap.setSingleStep(0.1)
        self.spin_gap.setValue(0.6)
        self.spin_gap.setSuffix(" 秒")
        self.params.add_layout(self._field("静音断句", self.spin_gap))

        lay.addWidget(self.params)

        # ---- 操作按钮 ----
        actions = QHBoxLayout()
        actions.setSpacing(8)

        self.btn_start = QPushButton("开始转写")
        self.btn_start.setObjectName("Primary")
        self.btn_start.setMinimumHeight(38)
        self.btn_start.clicked.connect(self._start)
        actions.addWidget(self.btn_start, 1)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("Danger")
        self.btn_cancel.setFixedWidth(82)
        self.btn_cancel.setMinimumHeight(38)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        actions.addWidget(self.btn_cancel)

        lay.addLayout(actions)

        return panel

    def _build_right(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        lay.addWidget(self.progress)

        self.lbl_stage = QLabel("就绪。把音视频文件拖进窗口，或点「添加文件」。")
        self.lbl_stage.setObjectName("Hint")
        lay.addWidget(self.lbl_stage)

        # ---- 每个文件一个标签页 ----
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(False)
        self.tabs.setMovable(True)
        self.tabs.setElideMode(Qt.ElideMiddle)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.empty_page = QLabel(
            "把音视频文件拖进窗口，或点左侧「添加文件」\n\n"
            "每个文件都会有自己的标签页，互不覆盖"
        )
        self.empty_page.setObjectName("EmptyHint")
        self.empty_page.setAlignment(Qt.AlignCenter)

        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(self.empty_page)
        self.right_stack.addWidget(self.tabs)
        self.right_stack.setCurrentIndex(0)
        lay.addWidget(self.right_stack, 1)

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
        f.setObjectName("VLine")
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
        QShortcut(QKeySequence("Space"), self, self._toggle_play)
        QShortcut(QKeySequence("Ctrl+D"), self, self._toggle_theme)

    # ================================================================ 主题

    def _toggle_theme(self) -> None:
        self.theme = "dark" if self.theme != "dark" else "light"
        self.settings.setValue("theme", self.theme)
        self._apply_theme()

    def _apply_theme(self) -> None:
        from PySide6.QtWidgets import QApplication

        from .styles import build_stylesheet

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(self.theme))
        self.btn_theme.setText("日间模式" if self.theme == "dark" else "夜间模式")
        self.preview.canvas.set_border(palette(self.theme)["line"])
        self._refresh_model_badge()

    def _on_params_toggled(self, expanded: bool) -> None:
        """展开参数时把预览窗收矮一点，否则文件列表会被挤得只剩一行。"""
        self.preview.setFixedHeight(124 if expanded else 168)

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
        first_new = -1
        for p in paths:
            if any(d.path == p for d in self.docs):
                continue
            doc = self._create_doc(p)
            self.docs.append(doc)
            if first_new < 0:
                first_new = len(self.docs) - 1
            added += 1
        if not added:
            return

        self._refresh_file_list()
        self._status(f"已添加 {added} 个文件")
        if self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(0)
        elif first_new >= 0:
            self.file_list.setCurrentRow(first_new)

    def _create_doc(self, path: str) -> Document:
        doc = Document(path)
        view = DocView()
        view.set_hint(f"「{doc.name}」还没有转写结果。\n点左侧「开始转写」即可。")
        view.playRequested.connect(self._on_row_play)
        view.changed.connect(self._on_doc_edited)
        doc.view = view
        self.tabs.addTab(view, doc.name)
        index = self.tabs.count() - 1
        self.tabs.setTabToolTip(index, path)
        return doc

    def _clear_files(self) -> None:
        if not self.docs:
            return
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "提示", "正在转写，请先取消再清空。")
            return
        for doc in self.docs:
            TranscriptionPipeline.cleanup(doc.wav_path)
        self._syncing = True
        self.tabs.clear()
        self.docs.clear()
        self.current = None
        self._syncing = False
        self.preview.clear()
        self._refresh_file_list()
        self.btn_export.setEnabled(False)
        self.btn_play.setEnabled(False)
        self.lbl_stat.setText("—")
        self._status("已清空")

    def _refresh_file_list(self) -> None:
        self.file_list.blockSignals(True)
        cur = self.file_list.currentRow()
        self.file_list.clear()
        for doc in self.docs:
            mark = "●" if doc.done else "○"
            dur = self._fmt_dur(doc.duration)
            it = QListWidgetItem(f"{mark} {doc.name}\n{dur}  ·  {doc.status}")
            it.setToolTip(doc.path)
            self.file_list.addItem(it)
        if 0 <= cur < self.file_list.count():
            self.file_list.setCurrentRow(cur)
        self.file_list.blockSignals(False)
        self.lbl_count.setText(f"{len(self.docs)} 个")
        self.right_stack.setCurrentIndex(1 if self.docs else 0)

    @staticmethod
    def _fmt_dur(sec: float) -> str:
        if sec <= 0:
            return "时长未知"
        m, s = divmod(int(sec), 60)
        h, m = divmod(m, 60)
        return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"

    def _on_file_selected(self, row: int) -> None:
        if self._syncing or not (0 <= row < len(self.docs)):
            return
        self._syncing = True
        self.tabs.setCurrentIndex(row)
        self._syncing = False
        self._activate(self.docs[row])

    def _on_tab_changed(self, index: int) -> None:
        if self._syncing or not (0 <= index < len(self.docs)):
            return
        self._syncing = True
        self.file_list.setCurrentRow(index)
        self._syncing = False
        self._activate(self.docs[index])

    def _activate(self, doc: Document) -> None:
        """切换当前文件：换预览源、换导出按钮状态。"""
        if self.current is doc:
            self._sync_doc_buttons(doc)
            return
        self.preview.pause()
        self.current = doc
        self._probe_doc(doc)
        self.preview.load(doc.media_source(), doc.is_video)
        self._sync_doc_buttons(doc)
        if doc.result is not None:
            self.lbl_stat.setText(
                f"{len(doc.cues)} 条 · {self._fmt_dur(doc.result.duration_sec)}"
                f" · {doc.result.model_name}"
            )
            self.lbl_stage.setText(f"{doc.name}：{len(doc.cues)} 条字幕")
        else:
            self.lbl_stat.setText("—")
            self.lbl_stage.setText(f"{doc.name} · {doc.status}")

    def _sync_doc_buttons(self, doc: Document) -> None:
        self.btn_play.setEnabled(self.preview.available and bool(doc.cues))
        self.btn_export.setEnabled(bool(doc.cues))

    def _probe_doc(self, doc: Document) -> None:
        if doc.duration > 0:
            return
        try:
            info = probe(doc.path)
            doc.duration = info.duration_sec
            if not info.has_audio:
                doc.status = "无音轨"
            self._refresh_file_list()
        except Exception as exc:
            doc.status = "读取失败"
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
        if not self.docs:
            QMessageBox.information(self, "提示", "请先添加文件。")
            return

        try:
            find_ffmpeg()
        except Exception as exc:
            QMessageBox.critical(self, "缺少 ffmpeg", str(exc))
            return

        # 队列：当前文件优先，其余未转写的一起排队
        cur = self.current
        pending = [d for d in self.docs if not d.done and d.status != "无音轨"]
        if not pending and cur is not None and cur.done:
            pending = [cur]        # 全转完了，允许重转当前这一个
        if not pending:
            QMessageBox.information(self, "提示", "所有文件都已转写完成。")
            return
        if cur in pending:
            pending.remove(cur)
            pending.insert(0, cur)

        self._queue = pending
        self._batch_total = len(pending)
        self._batch_done = 0
        self._batch_failed = 0
        self._set_busy(True)
        self._start_next()

    def _start_next(self) -> None:
        if not self._queue:
            self._finish_batch()
            return

        doc = self._queue.pop(0)
        self._worker_doc = doc
        doc.status = "转写中"
        self._refresh_file_list()
        # 转写中的文件自动切到它的标签页，用户能立刻看到进度对应的文件
        self._goto(doc)

        self.progress.setValue(0)
        self._set_progress_state(None)
        idx = self.docs.index(doc) + 1
        self._status(f"开始转写（{idx}/{self._batch_total}）：{doc.name}")
        self.lbl_stage.setText(f"正在处理 {doc.name}")

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

        engine = self._ensure_engine()
        self._worker = TranscribeWorker(engine, doc.path, cfg, parent=self)
        self._worker.progressed.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_fail)
        self._worker.cancelled.connect(self._on_cancel)
        self._worker.start()

    def _goto(self, doc: Document) -> None:
        row = self.docs.index(doc)
        self._syncing = True
        self.file_list.setCurrentRow(row)
        self.tabs.setCurrentIndex(row)
        self._syncing = False
        self._activate(doc)

    def _cancel(self) -> None:
        self._queue.clear()
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
        doc = self._worker_doc
        self._worker_doc = None
        if doc is None:
            return

        doc.result = result
        doc.wav_path = result.wav_path
        doc.cues = list(result.cues)
        if doc.view is not None:
            doc.view.set_cues(doc.cues)
        doc.status = f"完成 {len(doc.cues)} 条"
        self._batch_done += 1
        self._refresh_file_list()

        if doc is self.current:
            self.btn_export.setEnabled(bool(doc.cues))
            self.btn_play.setEnabled(self.preview.available and bool(doc.cues))
            self.preview.load(doc.media_source(), doc.is_video)
            speed = result.duration_sec / max(result.elapsed_sec, 1e-6)
            self.lbl_stage.setText(
                f"完成：{len(doc.cues)} 条字幕，用时 {result.elapsed_sec:.1f}s"
                f"（约 {speed:.1f}× 实时）"
            )
            self.lbl_stat.setText(
                f"{len(doc.cues)} 条 · {self._fmt_dur(result.duration_sec)} · {result.model_name}"
            )
        self._status(f"{doc.name} 转写完成")

        self.progress.setValue(1000)
        self._set_progress_state("done")
        self._start_next()

    def _on_fail(self, message: str) -> None:
        doc = self._worker_doc
        self._worker_doc = None
        self._batch_failed += 1
        if doc is not None:
            doc.status = "失败"
            if doc.view is not None:
                doc.view.set_hint(f"「{doc.name}」转写失败\n{message}")
            self._refresh_file_list()
        self.progress.setValue(1000)
        self._set_progress_state("failed")
        self.lbl_stage.setText("转写失败")
        self._status("转写失败")
        # 批量时不弹窗打断，最后统一汇总
        if self._batch_total <= 1:
            QMessageBox.critical(self, "转写失败", message)
        self._start_next()

    def _on_cancel(self) -> None:
        doc = self._worker_doc
        self._worker_doc = None
        if doc is not None and not doc.done:
            doc.status = "已取消"
        self._queue.clear()
        self._set_busy(False)
        self.progress.setValue(0)
        self._set_progress_state(None)
        self.lbl_stage.setText("已取消")
        self._refresh_file_list()
        self._status("已取消")

    def _finish_batch(self) -> None:
        self._set_busy(False)
        msg = f"全部完成：成功 {self._batch_done} 个"
        if self._batch_failed:
            msg += f"，失败 {self._batch_failed} 个"
        self._status(msg)
        self.lbl_stage.setText(msg)

    # ================================================================ 播放

    def _toggle_play(self) -> None:
        doc = self.current
        if doc is None or not doc.cues or not self.preview.available:
            return
        view = doc.view
        row = view.current_row() if view is not None else -1
        if row < 0:
            row = 0
        self._on_row_play(row)

    def _on_row_play(self, row: int) -> None:
        doc = self.current
        if doc is None or not (0 <= row < len(doc.cues)):
            return
        if not self.preview.available:
            self._status("播放组件不可用")
            return
        cue = doc.cues[row]
        # 提前 150ms 起播，避免开头吞字
        self.preview.play_from(max(0, cue.start_ms - 150), cue.end_ms)

    def _on_preview_pos(self, pos: int) -> None:
        self.lbl_pos.setText(ms_to_srt(pos))
        doc = self.current
        if doc is None or not doc.cues or doc.view is None:
            return
        # 播放时让表格跟着走，标出当前这句
        if not self.preview.is_playing:
            return
        for i, cue in enumerate(doc.cues):
            if cue.start_ms <= pos < cue.end_ms:
                doc.view.highlight_row(i)
                break

    def _on_playing_changed(self, playing: bool) -> None:
        self.btn_play.setText("■ 停止" if playing else "▶ 播放选中")
        self.btn_play_prev.setText("■ 停止" if playing else "▶ 播放")
        if not playing:
            self.preview.set_stop_at(-1)

    # ================================================================ 编辑

    def _on_doc_edited(self) -> None:
        doc = self.current
        if doc is None:
            return
        doc.dirty = True
        if doc.view is not None:
            doc.cues = doc.view.cues
        self.lbl_stat.setText(f"{len(doc.cues)} 条（已手工修改）")

    # ================================================================ 导出

    def _export(self) -> None:
        doc = self.current
        if doc is None or not doc.cues:
            return
        cues = doc.view.cues if doc.view is not None else doc.cues

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

        default_dir = os.path.dirname(doc.path) or os.path.expanduser("~")
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

        problems = exporters.validate(cues)
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
            written = exporters.export(cues, opt, doc.path, out_dir)
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
        colors = palette(self.theme)
        if kind == "sensevoice":
            self.badge_model.setText("● 模型已就绪 · SenseVoice")
            self.badge_model.setStyleSheet(f"color: {colors['ok']};")
        else:
            self.badge_model.setText("● 未找到模型 · 演示模式")
            self.badge_model.setStyleSheet(f"color: {colors['warn']};")
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
        for doc in self.docs:
            TranscriptionPipeline.cleanup(doc.wav_path)
        self.settings.sync()
        event.accept()

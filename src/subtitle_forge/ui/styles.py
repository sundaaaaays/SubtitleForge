# -*- coding: utf-8 -*-
"""界面样式表。

QSS 用 __TOKEN__ 占位符写，LIGHT / DARK 两套调色板在 build_stylesheet() 里
统一替换，这样不必维护两份几乎一样的样式表。

不要在这里直接写死颜色：加了硬编码色值之后，切到暗色主题就会露出一块浅底。
"""
from __future__ import annotations

import os
import sys

LIGHT = {
    "bg": "#ffffff",
    "bg_soft": "#f7f7f5",
    "bg_nav": "#fbfbfa",
    "fg": "#1f2328",
    "fg2": "#57606a",
    "fg3": "#8b949e",
    "line": "#e4e4e0",
    "line_strong": "#d0d0ca",
    "accent": "#c0392b",
    "accent_hover": "#a93226",
    "accent_soft": "#fdf2f0",
    "on_accent": "#ffffff",
    "accent_disabled": "#e3b7b1",
    "ok": "#1a7f37",
    "warn": "#9a6700",
    "err": "#cf222e",
    "disabled_fg": "#b0b0aa",
    "disabled_bg": "#fafaf9",
    "disabled_border": "#ececea",
    "btn_hover_bg": "#f7f7f5",
    "btn_press_bg": "#efefec",
    "header_bg": "#f2f1ee",
    "row_alt": "#fcfcfb",
    "grid": "#f0f0ec",
    "scroll": "#d8d8d2",
    "scroll_hover": "#c0c0ba",
    "input_bg": "#ffffff",
    "spin_bg": "#fafaf9",
    "spin_hover": "#f0efec",
    "tooltip_bg": "#1f2328",
    "tooltip_fg": "#ffffff",
    "video_bg": "#0e1013",
    "tab_bg": "#f2f1ee",
    "tab_sel_bg": "#ffffff",
}

DARK = {
    "bg": "#17191f",
    "bg_soft": "#1f232b",
    "bg_nav": "#1b1e25",
    "fg": "#e6e8ec",
    "fg2": "#9aa4b2",
    "fg3": "#7c8695",
    "line": "#2b303a",
    "line_strong": "#3a414d",
    "accent": "#e2564a",
    "accent_hover": "#f06a5c",
    "accent_soft": "#2d1d1b",
    "on_accent": "#ffffff",
    "accent_disabled": "#6b3b35",
    "ok": "#4bc46e",
    "warn": "#d6a72c",
    "err": "#ff6b6b",
    "disabled_fg": "#5c6472",
    "disabled_bg": "#1b1e24",
    "disabled_border": "#2b303a",
    "btn_hover_bg": "#232830",
    "btn_press_bg": "#2c323c",
    "header_bg": "#222731",
    "row_alt": "#1a1d23",
    "grid": "#262b34",
    "scroll": "#3a414d",
    "scroll_hover": "#4b535f",
    "input_bg": "#1e222a",
    "spin_bg": "#232830",
    "spin_hover": "#2c323c",
    "tooltip_bg": "#e6e8ec",
    "tooltip_fg": "#17191f",
    "video_bg": "#0b0d10",
    "tab_bg": "#1e222a",
    "tab_sel_bg": "#17191f",
}

# 兼容旧代码：默认取浅色调色板
COLORS = dict(LIGHT)

QSS = """
QWidget {
    background: __BG__;
    color: __FG__;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog { background: __BG__; }

/* 标签默认透明，否则会在深色顶栏上留下一块底色 */
QLabel { background: transparent; }

/* ---------- 标题区 ---------- */
#HeaderTitle {
    font-size: 19px;
    font-weight: 600;
    color: __FG__;
    letter-spacing: 0.5px;
}
#HeaderSub {
    font-size: 12px;
    color: __FG3__;
}
#HeaderBar {
    background: __BG_NAV__;
    border-bottom: 1px solid __LINE__;
}

/* ---------- 卡片 ---------- */
#Card {
    background: __BG__;
    border: 1px solid __LINE__;
    border-radius: 8px;
}
#CardTitle {
    font-size: 13px;
    font-weight: 600;
    color: __FG__;
    padding-bottom: 2px;
}
#Hint {
    color: __FG3__;
    font-size: 12px;
}
#EmptyHint {
    color: __FG3__;
    font-size: 13px;
}

/* ---------- 按钮 ---------- */
QPushButton {
    background: __BG__;
    border: 1px solid __LINE_STRONG__;
    border-radius: 6px;
    padding: 6px 14px;
    color: __FG__;
    min-height: 18px;
}
QPushButton:hover { background: __BTN_HOVER_BG__; border-color: __SCROLL_HOVER__; }
QPushButton:pressed { background: __BTN_PRESS_BG__; }
QPushButton:disabled {
    color: __DISABLED_FG__;
    border-color: __DISABLED_BORDER__;
    background: __DISABLED_BG__;
}

QPushButton#Primary {
    background: __ACCENT__;
    border: 1px solid __ACCENT__;
    color: __ON_ACCENT__;
    font-weight: 600;
    padding: 8px 20px;
}
QPushButton#Primary:hover { background: __ACCENT_HOVER__; border-color: __ACCENT_HOVER__; }
QPushButton#Primary:disabled {
    background: __ACCENT_DISABLED__;
    border-color: __ACCENT_DISABLED__;
    color: __ON_ACCENT__;
}

QPushButton#Danger {
    background: __BG__;
    border: 1px solid __ERR__;
    color: __ERR__;
}
QPushButton#Danger:hover { background: __ACCENT_SOFT__; }
QPushButton#Danger:disabled {
    border-color: __DISABLED_BORDER__;
    color: __DISABLED_FG__;
    background: __DISABLED_BG__;
}

/* 折叠头：整条可点，去掉按钮感 */
QPushButton#CollapseHead {
    background: transparent;
    border: none;
    padding: 0;
    text-align: left;
    font-weight: 600;
    color: __FG__;
}
QPushButton#CollapseHead:hover { background: transparent; }

/* 图标按钮（主题切换、预览占位） */
QPushButton#Ghost {
    background: transparent;
    border: 1px solid __LINE__;
    padding: 4px 10px;
}
QPushButton#Ghost:hover { background: __BTN_HOVER_BG__; }

/* ---------- 输入 ---------- */
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background: __INPUT_BG__;
    border: 1px solid __LINE_STRONG__;
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 18px;
    color: __FG__;
    selection-background-color: __ACCENT__;
    selection-color: __ON_ACCENT__;
}
QComboBox { padding-right: 26px; }
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border-color: __ACCENT__;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 22px;
    border: none;
}
QComboBox::down-arrow {
    image: url("__ASSETS__/arrow-down.svg");
    width: 10px;
    height: 6px;
}
QComboBox QAbstractItemView {
    border: 1px solid __LINE_STRONG__;
    background: __INPUT_BG__;
    color: __FG__;
    selection-background-color: __ACCENT_SOFT__;
    selection-color: __ACCENT__;
    outline: none;
    padding: 3px;
}

/* ---- 数字输入框的上下按钮 ---- */
QSpinBox, QDoubleSpinBox { padding-right: 20px; }
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 17px;
    margin: 1px 1px 0 0;
    border-left: 1px solid __DISABLED_BORDER__;
    border-top-right-radius: 5px;
    background: __SPIN_BG__;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 17px;
    margin: 0 1px 1px 0;
    border-left: 1px solid __DISABLED_BORDER__;
    border-bottom-right-radius: 5px;
    background: __SPIN_BG__;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background: __SPIN_HOVER__;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("__ASSETS__/arrow-up.svg");
    width: 8px; height: 5px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("__ASSETS__/arrow-down.svg");
    width: 8px; height: 5px;
}

QCheckBox { spacing: 6px; color: __FG__; }
QCheckBox::indicator {
    width: 15px; height: 15px;
    border: 1px solid __SCROLL_HOVER__;
    border-radius: 3px;
    background: __INPUT_BG__;
}
QCheckBox::indicator:hover { border-color: __ACCENT__; }
QCheckBox::indicator:checked {
    background: __ACCENT__;
    border-color: __ACCENT__;
    image: url("__ASSETS__/check.svg");
}

QSlider::groove:horizontal {
    height: 4px; background: __LINE__; border-radius: 2px;
}
QSlider::sub-page:horizontal { background: __ACCENT__; border-radius: 2px; }
QSlider::handle:horizontal {
    background: __BG__; border: 2px solid __ACCENT__;
    width: 12px; height: 12px; margin: -6px 0; border-radius: 8px;
}

/* ---------- 表格 ---------- */
QTableWidget {
    background: __BG__;
    border: 1px solid __LINE__;
    border-radius: 6px;
    gridline-color: __GRID__;
    selection-background-color: __ACCENT_SOFT__;
    selection-color: __FG__;
    alternate-background-color: __ROW_ALT__;
    color: __FG__;
}
QTableWidget::item { padding: 5px 6px; border: none; }
QTableWidget::item:selected { background: __ACCENT_SOFT__; color: __FG__; }
QHeaderView::section {
    background: __HEADER_BG__;
    color: __FG__;
    font-weight: 600;
    border: none;
    border-bottom: 1px solid __LINE_STRONG__;
    border-right: 1px solid __LINE__;
    padding: 7px 6px;
}
QHeaderView::section:last { border-right: none; }
QTableCornerButton::section { background: __HEADER_BG__; border: none; }

/* ---------- 列表 ---------- */
QListWidget {
    background: __BG__;
    border: 1px solid __LINE__;
    border-radius: 6px;
    outline: none;
    padding: 3px;
    color: __FG__;
}
QListWidget::item {
    padding: 8px 10px;
    border-radius: 5px;
    margin: 1px 0;
}
QListWidget::item:hover { background: __BTN_HOVER_BG__; }
QListWidget::item:selected { background: __ACCENT_SOFT__; color: __FG__; }

/* ---------- 标签页（每个文件一个） ---------- */
QTabWidget::pane {
    border: 1px solid __LINE__;
    border-radius: 8px;
    background: __BG__;
    top: -1px;
}
QTabBar { qproperty-drawBase: 0; }
QTabBar::tab {
    background: __TAB_BG__;
    color: __FG2__;
    border: 1px solid __LINE__;
    border-bottom: none;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    padding: 7px 14px;
    margin-right: 3px;
    max-width: 220px;
}
QTabBar::tab:selected {
    background: __TAB_SEL_BG__;
    color: __FG__;
    font-weight: 600;
}
QTabBar::tab:hover:!selected { background: __BTN_HOVER_BG__; }
QTabBar::close-button {
    image: none;
    subcontrol-position: right;
}

/* ---------- 进度 ---------- */
QProgressBar {
    background: __BTN_PRESS_BG__;
    border: none;
    border-radius: 3px;
    height: 6px;
    max-height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: __ACCENT__;
    border-radius: 3px;
}
QProgressBar[done="true"]::chunk { background: __OK__; }
QProgressBar[failed="true"]::chunk { background: __ERR__; }

/* ---------- 状态栏 ---------- */
QStatusBar {
    background: __BG_NAV__;
    border-top: 1px solid __LINE__;
    color: __FG2__;
    font-size: 12px;
}
QStatusBar::item { border: none; }

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {
    background: transparent; width: 10px; margin: 0;
}
QScrollBar::handle:vertical {
    background: __SCROLL__; border-radius: 5px; min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: __SCROLL_HOVER__; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal {
    background: __SCROLL__; border-radius: 5px; min-width: 28px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ---------- 其他 ---------- */
QToolTip {
    background: __TOOLTIP_BG__; color: __TOOLTIP_FG__;
    border: none; padding: 5px 8px; border-radius: 4px;
}
QSplitter::handle { background: __LINE__; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }
QLabel#SectionLabel { color: __FG2__; font-size: 12px; font-weight: 600; }
QFrame#Divider { background: __LINE__; max-height: 1px; border: none; }
QFrame#VLine { background: __LINE__; max-width: 1px; border: none; }
"""

# 视频画布（#VideoStage）由 VideoCanvas.paintEvent 自绘背景与边框，
# 不走样式表，这里不提供它的规则。


def palette(theme: str = "light") -> dict:
    return dict(DARK if theme == "dark" else LIGHT)


def assets_dir() -> str:
    """定位界面资源目录（箭头、勾选图标）。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 6.x 把 datas 放进 _internal/，运行时路径在 _MEIPASS
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    d = os.path.join(base, "assets")
    return d if os.path.isdir(d) else base


def build_stylesheet(theme: str = "light") -> str:
    """把占位符替换成真实路径与配色后返回 QSS。

    QSS 里 url() 必须用绝对路径，否则会相对于进程工作目录解析，打包后必然失效。
    占位符按长度倒序替换，避免 __BG__ 抢先吃掉 __BG_SOFT__ 这种前缀包含。
    """
    out = QSS.replace("__ASSETS__", assets_dir().replace("\\", "/"))
    colors = palette(theme)
    for key in sorted(colors, key=len, reverse=True):
        out = out.replace(f"__{key.upper()}__", colors[key])
    return out

# -*- coding: utf-8 -*-
"""界面样式表。浅色主题，与开发文档的排版风格保持一致。"""
from __future__ import annotations

import os
import sys

COLORS = {
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
    "ok": "#1a7f37",
    "warn": "#9a6700",
    "err": "#cf222e",
}

QSS = """
QWidget {
    background: #ffffff;
    color: #1f2328;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog { background: #ffffff; }

/* ---------- 标题区 ---------- */
#HeaderTitle {
    font-size: 19px;
    font-weight: 600;
    color: #1f2328;
    letter-spacing: 0.5px;
}
#HeaderSub {
    font-size: 12px;
    color: #8b949e;
}
#HeaderBar {
    background: #fbfbfa;
    border-bottom: 1px solid #e4e4e0;
}

/* ---------- 卡片 ---------- */
#Card {
    background: #ffffff;
    border: 1px solid #e4e4e0;
    border-radius: 8px;
}
#CardTitle {
    font-size: 13px;
    font-weight: 600;
    color: #1f2328;
    padding-bottom: 2px;
}
#Hint {
    color: #8b949e;
    font-size: 12px;
}

/* ---------- 按钮 ---------- */
QPushButton {
    background: #ffffff;
    border: 1px solid #d0d0ca;
    border-radius: 6px;
    padding: 6px 14px;
    color: #1f2328;
    min-height: 18px;
}
QPushButton:hover { background: #f7f7f5; border-color: #b8b8b2; }
QPushButton:pressed { background: #efefec; }
QPushButton:disabled { color: #b0b0aa; border-color: #e4e4e0; background: #fafaf9; }

QPushButton#Primary {
    background: #c0392b;
    border: 1px solid #c0392b;
    color: #ffffff;
    font-weight: 600;
    padding: 8px 20px;
}
QPushButton#Primary:hover { background: #a93226; border-color: #a93226; }
QPushButton#Primary:disabled { background: #e3b7b1; border-color: #e3b7b1; color: #ffffff; }

QPushButton#Danger {
    background: #ffffff;
    border: 1px solid #cf222e;
    color: #cf222e;
}
QPushButton#Danger:hover { background: #fdf2f0; }
QPushButton#Danger:disabled { border-color: #ececea; color: #b8b8b2; background: #fafaf9; }

/* ---------- 输入 ---------- */
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background: #ffffff;
    border: 1px solid #d0d0ca;
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 18px;
    selection-background-color: #c0392b;
    selection-color: #ffffff;
}
QComboBox { padding-right: 26px; }
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border-color: #c0392b;
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
    border: 1px solid #d0d0ca;
    background: #ffffff;
    selection-background-color: #fdf2f0;
    selection-color: #c0392b;
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
    border-left: 1px solid #ececea;
    border-top-right-radius: 5px;
    background: #fafaf9;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 17px;
    margin: 0 1px 1px 0;
    border-left: 1px solid #ececea;
    border-bottom-right-radius: 5px;
    background: #fafaf9;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background: #f0efec;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("__ASSETS__/arrow-up.svg");
    width: 8px; height: 5px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("__ASSETS__/arrow-down.svg");
    width: 8px; height: 5px;
}

QCheckBox { spacing: 6px; }
QCheckBox::indicator {
    width: 15px; height: 15px;
    border: 1px solid #c0c0ba;
    border-radius: 3px;
    background: #ffffff;
}
QCheckBox::indicator:hover { border-color: #c0392b; }
QCheckBox::indicator:checked {
    background: #c0392b;
    border-color: #c0392b;
    image: url("__ASSETS__/check.svg");
}

QSlider::groove:horizontal {
    height: 4px; background: #e4e4e0; border-radius: 2px;
}
QSlider::sub-page:horizontal { background: #c0392b; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #ffffff; border: 2px solid #c0392b;
    width: 12px; height: 12px; margin: -6px 0; border-radius: 8px;
}

/* ---------- 表格 ---------- */
QTableWidget {
    background: #ffffff;
    border: 1px solid #e4e4e0;
    border-radius: 6px;
    gridline-color: #f0f0ec;
    selection-background-color: #fdf2f0;
    selection-color: #1f2328;
    alternate-background-color: #fcfcfb;
}
QTableWidget::item { padding: 5px 6px; border: none; }
QTableWidget::item:selected { background: #fdf2f0; color: #1f2328; }
QHeaderView::section {
    background: #f2f1ee;
    color: #1f2328;
    font-weight: 600;
    border: none;
    border-bottom: 1px solid #d0d0ca;
    border-right: 1px solid #e4e4e0;
    padding: 7px 6px;
}
QHeaderView::section:last { border-right: none; }
QTableCornerButton::section { background: #f2f1ee; border: none; }

/* ---------- 列表 ---------- */
QListWidget {
    background: #ffffff;
    border: 1px solid #e4e4e0;
    border-radius: 6px;
    outline: none;
    padding: 3px;
}
QListWidget::item {
    padding: 8px 10px;
    border-radius: 5px;
    margin: 1px 0;
}
QListWidget::item:hover { background: #f7f7f5; }
QListWidget::item:selected { background: #fdf2f0; color: #1f2328; }

/* ---------- 进度 ---------- */
QProgressBar {
    background: #f0efec;
    border: none;
    border-radius: 3px;
    height: 6px;
    max-height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: #c0392b;
    border-radius: 3px;
}
QProgressBar[done="true"]::chunk { background: #2c8c4a; }
QProgressBar[failed="true"]::chunk { background: #cf222e; }

/* ---------- 状态栏 ---------- */
QStatusBar {
    background: #fbfbfa;
    border-top: 1px solid #e4e4e0;
    color: #57606a;
    font-size: 12px;
}
QStatusBar::item { border: none; }

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {
    background: transparent; width: 10px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #d8d8d2; border-radius: 5px; min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: #c0c0ba; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal {
    background: #d8d8d2; border-radius: 5px; min-width: 28px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ---------- 其他 ---------- */
QToolTip {
    background: #1f2328; color: #ffffff;
    border: none; padding: 5px 8px; border-radius: 4px;
}
QSplitter::handle { background: #e4e4e0; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }
QLabel#SectionLabel { color: #57606a; font-size: 12px; font-weight: 600; }
QFrame#Divider { background: #e4e4e0; max-height: 1px; border: none; }
"""


def assets_dir() -> str:
    """定位界面资源目录（箭头、勾选图标）。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 6.x 把 datas 放进 _internal/，运行时路径在 _MEIPASS
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    d = os.path.join(base, "assets")
    return d if os.path.isdir(d) else base


def build_stylesheet() -> str:
    """把 __ASSETS__ 占位符替换成真实路径后返回 QSS。

    QSS 里 url() 必须用绝对路径，否则会相对于进程工作目录解析，打包后必然失效。
    """
    path = assets_dir().replace("\\", "/")
    return QSS.replace("__ASSETS__", path)

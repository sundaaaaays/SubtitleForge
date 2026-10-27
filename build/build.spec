# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

产物是 onedir 形式（SubtitleForge 目录，内含 SubtitleForge.exe）。
选 onedir 而不是 onefile 的原因：PySide6 有 150MB+ 的 Qt 动态库，onefile
每次启动都要解压到临时目录，冷启动会慢 5~10 秒，体验很差。
"""
import os
import sys

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")

datas = [(os.path.join(ROOT, "assets"), "assets")]
binaries = []
hiddenimports = []

# sherpa-onnx 带 native dll 和 onnxruntime，必须全量收集
for pkg in ("sherpa_onnx", "imageio_ffmpeg"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += [
    "subtitle_forge",
    "subtitle_forge.ui.app",
    "subtitle_forge.ui.main_window",
    "subtitle_forge.ui.worker",
    "subtitle_forge.core.pipeline",
    "subtitle_forge.asr.sensevoice",
    "numpy",
]

# 用不到的重量级模块，排除后能省 100MB+
excludes = [
    "tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtQuickWidgets",
    "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSerialPort",
    "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtSql",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtRemoteObjects", "PySide6.QtSensors", "PySide6.QtNfc",
    "PySide6.QtHttpServer", "PySide6.QtWebSockets", "PySide6.QtWebChannel",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
]

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SubtitleForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # 不加壳：加壳是杀软误报的头号原因
    console=False,      # 无控制台窗口
    disable_windowed_traceback=False,
    icon=os.path.join(ROOT, "assets", "app.ico")
    if os.path.isfile(os.path.join(ROOT, "assets", "app.ico")) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="SubtitleForge",
)

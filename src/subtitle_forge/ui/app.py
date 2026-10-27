# -*- coding: utf-8 -*-
"""应用入口。"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow, app_root, resolve_model
from .styles import build_stylesheet


def _setup_font(app: QApplication) -> None:
    """优先用系统里的中文字体，避免某些机器上默认字体发虚。"""
    for family in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"):
        f = QFont(family)
        if f.exactMatch() or family.startswith("Microsoft YaHei"):
            app.setFont(QFont(family, 10))
            break


def cli_run(argv: list[str]) -> int:
    """无界面转写：SubtitleForge.exe --run a.mp4 --out D:\\out --format srt,txt

    既是批量处理入口，也用于验证打包产物能否跑通完整流程。
    结果日志写到 --log 指定文件（默认输入文件同目录的 subtitleforge.log）。
    """
    import traceback

    def arg(name: str, default: str = "") -> str:
        if name in argv:
            i = argv.index(name)
            if i + 1 < len(argv):
                return argv[i + 1]
        return default

    src = arg("--run") or os.environ.get("SF_RUN", "")
    out_dir = arg("--out") or os.environ.get("SF_OUT") or (
        os.path.dirname(os.path.abspath(src)) if src else os.getcwd()
    )
    formats = [f.strip() for f in arg("--format", "srt,txt").split(",") if f.strip()]
    lang = arg("--lang", "auto")
    env = arg("--env", "quiet")

    log_path = arg("--log") or os.environ.get("SF_LOG") or os.path.join(out_dir, "subtitleforge.log")
    if getattr(sys, "frozen", False):
        log_path = log_path or os.path.join(
            os.path.dirname(os.path.abspath(sys.executable)), "subtitleforge.log"
        )
    lines: list[str] = []

    def log(msg: str) -> None:
        lines.append(msg)

    # 无论成败都先记下真实入参，排查"参数没传到"这类问题时这是唯一线索
    log(f"frozen={getattr(sys, 'frozen', False)}")
    log(f"argv={argv!r}")
    log(f"src={src!r} exists={os.path.isfile(src) if src else False}")
    log(f"out_dir={out_dir!r} log_path={log_path!r}")

    if not src or not os.path.isfile(src):
        log("CLI_FAILED: 输入文件不存在或未提供 --run")
        try:
            os.makedirs(out_dir or ".", exist_ok=True)
        except Exception:
            log_path = os.path.join(os.getcwd(), "subtitleforge.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return 2

    code = 0
    try:
        from ..core import exporters as ex
        from ..core.models import ExportOptions, SplitOptions
        from ..core.pipeline import TranscribeConfig, TranscriptionPipeline

        kind, kw = resolve_model()
        log(f"engine={kind}")
        if kind != "sensevoice":
            # 演示引擎只会输出占位文本，批量场景下必须让调用方知道，不能静默成功
            log("CLI_FAILED: 未找到 SenseVoice 模型")
            log("请把 model.int8.onnx 与 tokens.txt 放到 "
                f"{os.path.join(app_root(), 'models', 'sensevoice')}")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return 3

        if kind == "sensevoice":
            from ..asr.sensevoice import SenseVoiceEngine

            engine = SenseVoiceEngine(
                kw["model_path"], kw["tokens_path"], language=lang,
                num_threads=max(2, min(8, (os.cpu_count() or 4) - 1)),
            )
        else:
            from ..core.pipeline import DemoEngine

            engine = DemoEngine()

        cfg = TranscribeConfig(language=lang, environment=env, split=SplitOptions())
        pipe = TranscriptionPipeline(engine)

        def on_progress(p) -> None:
            log(f"[{p.stage}] {p.ratio*100:5.1f}% {p.message}")

        result = pipe.run(src, cfg, progress=on_progress)
        log(f"duration={result.duration_sec:.2f}s elapsed={result.elapsed_sec:.2f}s "
            f"cues={len(result.cues)}")

        opt = ExportOptions(formats=formats)
        written = ex.export(result.cues, opt, src, out_dir)
        for p in written:
            log(f"written={p}")
        log("CLI_OK")
    except Exception:
        log("CLI_FAILED")
        log(traceback.format_exc())
        code = 1

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return code


def selftest() -> int:
    """打包后自检：验证模块、模型、ffmpeg 是否齐全。

    用 ``SubtitleForge.exe --selftest`` 调用，结果写到 exe 旁的 selftest.log。
    GUI 程序没有控制台，只能靠日志文件回传结果。
    """
    import traceback

    lines: list[str] = []
    code = 0
    try:
        lines.append(f"frozen={getattr(sys, 'frozen', False)}")
        lines.append(f"exe={sys.executable}")
        lines.append(f"app_root={app_root()}")

        import numpy
        import sherpa_onnx

        lines.append(f"numpy={numpy.__version__}  sherpa_onnx={sherpa_onnx.__version__}")

        from ..audio.decoder import find_ffmpeg

        lines.append(f"ffmpeg={find_ffmpeg()}")

        kind, kw = resolve_model()
        lines.append(f"model_kind={kind}")

        if kind == "sensevoice":
            from ..asr.sensevoice import SenseVoiceEngine

            eng = SenseVoiceEngine(kw["model_path"], kw["tokens_path"])
            eng.initialize()
            lines.append("engine_loaded=True")
            res = eng.transcribe(numpy.zeros(16000, dtype=numpy.float32))
            lines.append(f"transcribe_silence_ok text={res.text!r}")
            eng.release()

        lines.append("SELFTEST OK")
    except Exception:
        lines.append("SELFTEST FAILED")
        lines.append(traceback.format_exc())
        code = 1

    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.getcwd()
    with open(os.path.join(base, "selftest.log"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return code


def _startup_log(lines: list[str]) -> None:
    """把启动状态写到 exe 旁的 startup.log，用于验证打包产物。"""
    try:
        if getattr(sys, "frozen", False):
            base = os.path.dirname(os.path.abspath(sys.executable))
        else:
            base = os.getcwd()
        with open(os.path.join(base, "startup.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv

    boot: list[str] = []
    boot.append(f"frozen={getattr(sys, 'frozen', False)}")
    boot.append(f"argv={argv!r}")
    boot.append(f"_MEIPASS={getattr(sys, '_MEIPASS', None)}")
    boot.append(f"SF_RUN={os.environ.get('SF_RUN')!r}")

    # 诊断：--argsdump 时把真实收到的命令行写到文件
    if "--argsdump" in argv or os.environ.get("SF_ARGSDUMP"):
        base = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else os.getcwd()
        with open(os.path.join(base, "args.log"), "w", encoding="utf-8") as f:
            f.write(f"frozen={getattr(sys, 'frozen', False)}\n")
            f.write("argv=" + repr(argv) + "\n")
            f.write("SF_RUN=" + repr(os.environ.get("SF_RUN")) + "\n")
        return 0

    if "--selftest" in argv:
        return selftest()

    if "--run" in argv or os.environ.get("SF_RUN"):
        return cli_run(argv)

    # 高 DPI 缩放：Qt6 默认已启用，这里只保证不出现小数缩放导致的模糊
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    from .styles import assets_dir

    adir = assets_dir()
    boot.append(f"assets_dir={adir}")
    for name in ("arrow-down.svg", "arrow-up.svg", "check.svg"):
        boot.append(f"  {name}: {os.path.isfile(os.path.join(adir, name))}")
    qss = build_stylesheet()
    boot.append(f"qss_len={len(qss)} placeholder_left={'__ASSETS__' in qss}")

    app = QApplication(argv)
    app.setApplicationName("SubtitleForge")
    app.setApplicationDisplayName("字幕工坊")
    app.setOrganizationName("SubtitleForge")
    _setup_font(app)
    app.setStyleSheet(build_stylesheet())

    win = MainWindow()
    boot.append("mainwindow_built=True")
    win.show()
    boot.append(f"shown=True size={win.width()}x{win.height()}")
    _startup_log(boot)

    # 打包验证用：--screenshot <路径>，延时截取窗口后退出
    shot_target = None
    if "--screenshot" in argv:
        idx = argv.index("--screenshot")
        if idx + 1 < len(argv):
            shot_target = argv[idx + 1]
    if shot_target:
        import traceback

        from PySide6.QtCore import QTimer

        def _grab() -> None:
            try:
                ok = win.grab().save(shot_target)
                msg = f"save_ok={ok}\npath={shot_target}"
            except Exception:
                msg = "GRAB FAILED\n" + traceback.format_exc()
            try:
                with open(shot_target + ".log", "w", encoding="utf-8") as f:
                    f.write(msg)
            except Exception:
                pass
            win.close()
            app.quit()

        QTimer.singleShot(1600, _grab)

    # 支持把文件拖到 exe 图标或用命令行传入
    extra = [a for a in argv[1:] if os.path.isfile(a)]
    if extra:
        win._add_files(extra)

    return app.exec()

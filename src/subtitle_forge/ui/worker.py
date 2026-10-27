# -*- coding: utf-8 -*-
"""后台转写线程。所有耗时工作在子线程里跑，主线程只更新界面。"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..core.pipeline import (
    Cancelled,
    Progress,
    TranscribeConfig,
    TranscriptionPipeline,
)


class TranscribeWorker(QThread):
    """执行一次完整转写。通过信号把进度和结果回传主线程。"""

    progressed = Signal(str, float, str, int)   # stage, ratio, message, cue_count
    succeeded = Signal(object)                  # TranscriptionResult
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, engine, source_path: str, config: TranscribeConfig, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._source = source_path
        self._config = config
        self._cancel_flag = False

    def request_cancel(self) -> None:
        self._cancel_flag = True

    # ---------------------------------------------------------------- 线程体

    def run(self) -> None:  # noqa: D102
        pipeline = TranscriptionPipeline(self._engine)
        try:
            result = pipeline.run(
                self._source,
                self._config,
                progress=self._on_progress,
                should_cancel=lambda: self._cancel_flag,
            )
            if self._cancel_flag:
                self.cancelled.emit()
            else:
                self.succeeded.emit(result)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:  # 任何异常都要回传，不能让线程静默死掉
            self.failed.emit(f"{type(exc).__name__}: {exc}")

    def _on_progress(self, p: Progress) -> None:
        self.progressed.emit(p.stage, p.ratio, p.message, p.cue_count)

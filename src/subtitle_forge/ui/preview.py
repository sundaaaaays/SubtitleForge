# -*- coding: utf-8 -*-
"""左侧的视频预览窗。

播放器只在这里持有一份：既给视频出画面，也给音频出声。点字幕行时
seek 到这个时间点，播放过程中把位置回传给主窗口做行高亮。

画面没有用 QVideoWidget，而是把 QVideoSink 送来的帧自己画到画布上。
原因：QVideoWidget 走独立原生表面，截图/录屏抓不到（全黑），
圆角和样式表也容易被它顶掉；自绘虽然多几次像素拷贝，但行为完全可预期。
"""
from __future__ import annotations

import os
import time

from PySide6.QtCore import QRect, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..core.textutil import ms_to_short

STAGE_BG = QColor("#0b0d10")
BORDER = "#2b303a"
MAX_FPS = 30.0          # 再高人也看不出来，白白烧 CPU


class VideoCanvas(QWidget):
    """把解码帧等比缩放居中画出来。没有帧时显示提示文字。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VideoStage")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._image: QImage | None = None
        self._hint = "视频预览\n添加文件后在这里显示画面"
        self._border = BORDER

    def set_border(self, color: str) -> None:
        self._border = color
        self.update()

    def set_hint(self, text: str) -> None:
        self._hint = text
        self._image = None
        self.update()

    def set_frame(self, img: QImage) -> None:
        self._image = img
        self.update()

    def clear(self) -> None:
        self._image = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        rect = self.rect()
        painter.fillRect(rect, STAGE_BG)
        if self._image is not None and not self._image.isNull():
            target = self._fit(self._image.size(), rect.size())
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawImage(target, self._image)
        else:
            painter.setPen(QColor("#7c8695"))
            painter.drawText(rect, Qt.AlignCenter, self._hint)
        # 边框自己画，省得和样式表抢绘制
        painter.setPen(QColor(self._border))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.end()

    @staticmethod
    def _fit(src, box) -> QRect:
        """等比缩放到 box 内并居中，避免画面被拉扁。"""
        sw, sh = max(1, src.width()), max(1, src.height())
        bw, bh = max(1, box.width()), max(1, box.height())
        scale = min(bw / sw, bh / sh)
        w, h = int(sw * scale), int(sh * scale)
        return QRect((bw - w) // 2, (bh - h) // 2, w, h)


class PreviewPanel(QWidget):
    positionChanged = Signal(int)
    playingChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = None
        self._audio = None
        self._sink = None
        self._stop_at = -1
        self._dragging = False
        self._last_frame_ts = 0.0

        self.canvas = VideoCanvas()
        self.canvas.setMinimumHeight(120)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderPressed.connect(self._on_drag_start)
        self.slider.sliderReleased.connect(self._on_drag_end)
        self.slider.sliderMoved.connect(self._on_drag_move)

        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setObjectName("Hint")

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(8)
        bottom.addWidget(self.slider, 1)
        bottom.addWidget(self.lbl_time)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(self.canvas, 1)
        lay.addLayout(bottom)

        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)

        self._init_player()

    # ---------------------------------------------------------------- 初始化

    def _init_player(self) -> None:
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink

            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._audio.setVolume(0.85)
            self._player.setAudioOutput(self._audio)
            # 必须显式挂一个 videoSink，否则播放器认为没有视频消费者、根本不吐帧
            self._sink = QVideoSink(self)
            self._player.setVideoOutput(self._sink)
            self._sink.videoFrameChanged.connect(self._on_frame)
        except Exception:
            self._player = None
            self.canvas.set_hint("播放组件不可用\n（不影响转写与导出）")
            return

        self._player.positionChanged.connect(self._on_position)

    @property
    def available(self) -> bool:
        return self._player is not None

    @property
    def has_video_output(self) -> bool:
        return self._player is not None

    @property
    def is_playing(self) -> bool:
        if self._player is None:
            return False
        return self._player.playbackState() == self._player.PlaybackState.PlayingState

    @property
    def canvas_widget(self) -> VideoCanvas:
        return self.canvas

    # ---------------------------------------------------------------- 载入

    def load(self, path: str, is_video: bool) -> None:
        """切换预览源。音频文件显示提示文字，视频文件抓帧显示。"""
        self._stop_at = -1
        self.slider.setRange(0, 0)
        self.lbl_time.setText("00:00 / 00:00")
        self.canvas.clear()

        if not path or not os.path.isfile(path):
            self.canvas.set_hint("没有可预览的媒体")
            self._stop()
            return

        if not is_video:
            self.canvas.set_hint(f"♪  {os.path.basename(path)}\n音频文件，无画面")
        else:
            self.canvas.set_hint("正在加载画面…")

        if self._player is None:
            return
        self._player.setSource(QUrl.fromLocalFile(path))

    def _on_frame(self, frame) -> None:
        if not frame.isValid():
            return
        now = time.monotonic()
        if now - self._last_frame_ts < 1.0 / MAX_FPS:
            return
        self._last_frame_ts = now
        img = frame.toImage()
        if not img.isNull():
            self.canvas.set_frame(img)

    def clear(self) -> None:
        self._stop()
        self.slider.setRange(0, 0)
        self.lbl_time.setText("00:00 / 00:00")
        self.canvas.set_hint("视频预览\n添加文件后在这里显示画面")
        if self._player is not None:
            self._player.setSource(QUrl())

    # ---------------------------------------------------------------- 播放

    def play_from(self, ms: int, stop_at: int = -1) -> None:
        if self._player is None:
            return
        self._stop_at = stop_at
        self._player.setPosition(max(0, ms))
        self._player.play()
        self._timer.start()
        self.playingChanged.emit(True)

    def toggle(self) -> None:
        if self._player is None:
            return
        if self.is_playing:
            self.pause()
        else:
            self._player.play()
            self._timer.start()
            self.playingChanged.emit(True)

    def pause(self) -> None:
        if self._player is None:
            return
        self._player.pause()
        self._timer.stop()
        self.playingChanged.emit(False)

    def _stop(self) -> None:
        if self._player is None:
            return
        self._player.stop()
        self._timer.stop()
        self.playingChanged.emit(False)

    def position(self) -> int:
        return self._player.position() if self._player is not None else 0

    def seek(self, ms: int) -> None:
        if self._player is None:
            return
        self._player.setPosition(max(0, ms))

    def set_stop_at(self, ms: int) -> None:
        self._stop_at = ms

    # ---------------------------------------------------------------- 滑块

    def _on_drag_start(self) -> None:
        self._dragging = True

    def _on_drag_move(self, value: int) -> None:
        self.lbl_time.setText(f"{ms_to_short(value)} / {ms_to_short(self.slider.maximum())}")

    def _on_drag_end(self) -> None:
        self._dragging = False
        self.seek(self.slider.value())

    def _on_position(self, pos: int) -> None:
        dur = self._player.duration() if self._player is not None else 0
        if dur > 0 and self.slider.maximum() != dur:
            self.slider.setRange(0, int(dur))
        if not self._dragging:
            self.slider.setValue(int(pos))
            self.lbl_time.setText(f"{ms_to_short(pos)} / {ms_to_short(dur)}")
        self.positionChanged.emit(int(pos))

    def _tick(self) -> None:
        if self._player is None:
            return
        if self._stop_at > 0 and self._player.position() >= self._stop_at:
            self.pause()
            self._stop_at = -1
            return
        if not self.is_playing:
            self._timer.stop()
            self.playingChanged.emit(False)

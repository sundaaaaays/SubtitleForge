# -*- coding: utf-8 -*-
"""生成应用图标（assets/app.ico）。

画一个红色圆角方块 + 白色「字」，再手工封装成 ICO（ICO 允许内嵌 PNG）。
"""
import os
import struct

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(ROOT, "assets")


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    # 圆角背景
    r = size * 0.22
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), r, r)
    p.fillPath(path, QColor("#c0392b"))

    # 底部两条短横线，暗示字幕条
    bar_h = max(2, int(size * 0.055))
    bar_y = size * 0.70
    p.setBrush(QColor(255, 255, 255, 110))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(size * 0.24, bar_y, size * 0.52, bar_h), bar_h / 2, bar_h / 2)
    p.drawRoundedRect(QRectF(size * 0.30, bar_y + bar_h * 2.4, size * 0.40, bar_h), bar_h / 2, bar_h / 2)

    # 主字
    f = QFont("Microsoft YaHei UI")
    f.setPixelSize(int(size * 0.46))
    f.setWeight(QFont.Bold)
    p.setFont(f)
    p.setPen(QColor("#ffffff"))
    p.drawText(QRectF(0, size * 0.06, size, size * 0.56), Qt.AlignCenter, "字")

    p.end()
    return img


def write_ico(pngs: list, out_path: str) -> None:
    """把多个尺寸的 PNG 封装成 ICO。"""
    n = len(pngs)
    header = struct.pack("<HHH", 0, 1, n)
    entries = b""
    offset = 6 + 16 * n
    blobs = []
    for size, data in pngs:
        w = 0 if size >= 256 else size
        h = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHIH", w, h, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs.append(data)

    with open(out_path, "wb") as f:
        f.write(header + entries + b"".join(blobs))


def main() -> None:
    app = QGuiApplication([])
    os.makedirs(OUT_DIR, exist_ok=True)

    pngs = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        img = render(size)
        tmp = os.path.join(OUT_DIR, f"_icon_{size}.png")
        img.save(tmp, "PNG")
        with open(tmp, "rb") as f:
            pngs.append((size, f.read()))
        os.remove(tmp)
        if size == 256:
            img.save(os.path.join(OUT_DIR, "app.png"), "PNG")

    # 手工封装的 ICO 会被 Win32 UpdateResource 拒绝（PyInstaller 报参数错误），
    # 改用 Qt 自带的 ICO 写入器，生成的是标准未压缩格式。
    ico = os.path.join(OUT_DIR, "app.ico")
    img256 = render(256)
    if not img256.save(ico, "ICO"):
        raise RuntimeError("ICO 写入失败")
    print(f"icon written: {ico}  ({os.path.getsize(ico)} bytes)")
    del app


if __name__ == "__main__":
    main()

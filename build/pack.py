# -*- coding: utf-8 -*-
"""一键打包：清旧产物 → PyInstaller → 放模型 → 自检。

用法（在项目根执行）：
    .venv\\Scripts\\python.exe build\\pack.py

为什么要这个脚本：手动敲命令有两个反复踩过的坑——

1. PyInstaller 的 --noconfirm 在清理旧 dist 目录时可能被安全策略拦截，
   结果是「构建成功」但产物还是上一次的。这里先把旧目录改名挪走，绕开删除。
2. `cp -r models/sensevoice dist/.../models/` 在目标目录不存在时会把
   sensevoice 的**内容**摊平进 models/，导致程序找不到模型、静默退化成
   演示引擎。这里显式建好 models/sensevoice 再拷。

最后跑一次 --selftest，把结果打印出来。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DIST = os.path.join(ROOT, "dist")
APP = os.path.join(DIST, "SubtitleForge")
PY = sys.executable


def log(msg: str) -> None:
    print(f"[pack] {msg}", flush=True)


def clear_old() -> None:
    """把旧产物改名挪走（不删除，避免触发批量删除保护）。"""
    if not os.path.isdir(APP):
        return
    stamp = time.strftime("%H%M%S")
    trash = os.path.join(DIST, f"_stale_{stamp}")
    try:
        os.rename(APP, trash)
        log(f"旧产物已挪到 {os.path.basename(trash)}")
    except OSError as exc:
        log(f"挪走旧产物失败（可能有文件被占用）：{exc}")
        raise SystemExit(1)


def build() -> None:
    log("开始构建…")
    log_path = os.path.join(ROOT, "build", "pack.log")
    with open(log_path, "w", encoding="utf-8", errors="replace") as f:
        proc = subprocess.run(
            [
                os.path.join(ROOT, ".venv", "Scripts", "pyinstaller.exe"),
                "--noconfirm", "--clean",
                "--distpath", "dist",
                "--workpath", "build/work",
                "build/build.spec",
            ],
            cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
        )
    if proc.returncode != 0 or not os.path.isfile(os.path.join(APP, "SubtitleForge.exe")):
        log(f"构建失败，详见 {log_path}")
        raise SystemExit(1)
    log("构建完成")


def copy_models() -> None:
    src = os.path.join(ROOT, "models", "sensevoice")
    if not os.path.isdir(src):
        log("警告：models/sensevoice 不存在，产物将只能走演示引擎")
        return
    dst = os.path.join(APP, "models", "sensevoice")
    os.makedirs(dst, exist_ok=True)
    for name in ("model.int8.onnx", "tokens.txt"):
        s = os.path.join(src, name)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(dst, name))
    log(f"模型已放入 models/sensevoice（{len(os.listdir(dst))} 个文件）")


def selftest() -> int:
    log("运行自检…")
    exe = os.path.join(APP, "SubtitleForge.exe")
    subprocess.run([exe, "--selftest"], cwd=APP, timeout=300)
    log_path = os.path.join(APP, "selftest.log")
    if not os.path.isfile(log_path):
        log("自检日志没有生成")
        return 1
    with open(log_path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    for line in text.splitlines():
        log(f"  {line}")
    return 0 if "SELFTEST OK" in text else 1


def main() -> int:
    clear_old()
    build()
    copy_models()
    code = selftest()
    size = 0
    for base, _dirs, files in os.walk(APP):
        for name in files:
            try:
                size += os.path.getsize(os.path.join(base, name))
            except OSError:
                pass
    log(f"产物大小 {size / 1024 / 1024:.0f} MB → {APP}")
    log("全部完成" if code == 0 else "自检未通过")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

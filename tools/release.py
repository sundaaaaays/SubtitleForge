# -*- coding: utf-8 -*-
"""发版：压缩 dist 产物 → 建 Release → 上传附件。

用法（项目根执行）：
    python tools\\release.py 0.1.0
    python tools\\release.py 0.2.0 --notes 自定义说明.md --draft

约定：产物目录 dist/SubtitleForge/ 已经由 build/pack.py 打好；
附件名固定为 SubtitleForge-v<版本>-win64.zip。

令牌从本机 Git 凭据管理器取（git credential fill），不落盘。
注意本机访问 GitHub 需要代理，若直连失败可先设环境变量：
    set https_proxy=http://127.0.0.1:25454
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DIST = os.path.join(ROOT, "dist")
APP_DIR = os.path.join(DIST, "SubtitleForge")
OWNER = "sundaaaaays"
REPO = "SubtitleForge"
API = f"https://api.github.com/repos/{OWNER}/{REPO}"

SEVEN_ZIP = r"C:\Program Files\7-Zip\7z.exe"
# 运行时产物不进压缩包
EXCLUDE_NAMES = {"selftest.log", "startup.log", "args.log"}


def log(msg: str) -> None:
    print(f"[release] {msg}", flush=True)


def token() -> str:
    out = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True,
    ).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit("取不到 GitHub 令牌，请先 git push 一次让凭据管理器记住")


def api(url: str, data: bytes | None = None, method: str = "GET",
        ctype: str = "application/json", tok: str = "") -> dict:
    r = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github+json",
        "Content-Type": ctype,
    })
    with urllib.request.urlopen(r, timeout=1800) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8")) if raw else {}


def make_zip(version: str) -> str:
    """压缩 dist/SubtitleForge 为 dist/SubtitleForge-v<版本>-win64.zip。"""
    if not os.path.isfile(os.path.join(APP_DIR, "SubtitleForge.exe")):
        raise SystemExit(f"找不到 {APP_DIR}\\SubtitleForge.exe，先跑 build/pack.py")

    for name in EXCLUDE_NAMES:
        p = os.path.join(APP_DIR, name)
        if os.path.isfile(p):
            os.remove(p)

    zip_path = os.path.join(DIST, f"SubtitleForge-v{version}-win64.zip")
    if os.path.isfile(zip_path):
        os.remove(zip_path)

    log("压缩中…")
    t0 = time.time()
    if os.path.isfile(SEVEN_ZIP):
        subprocess.run(
            [SEVEN_ZIP, "a", "-tzip", "-mx=5", "-mmt=on", zip_path, "SubtitleForge"],
            cwd=DIST, check=True, stdout=subprocess.DEVNULL,
        )
    else:
        shutil.make_archive(zip_path[:-4], "zip", DIST, "SubtitleForge")
    size = os.path.getsize(zip_path)
    log(f"压缩完成 {size / 1024 / 1024:.0f} MB，用时 {time.time() - t0:.0f}s")
    return zip_path


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("用法：python tools/release.py 0.1.0 [--notes 文件] [--draft]")
    version = args[0].lstrip("v")
    tag = f"v{version}"

    notes_path = os.path.join(ROOT, "docs", "release-notes.md")
    if "--notes" in sys.argv:
        notes_path = sys.argv[sys.argv.index("--notes") + 1]
    body = open(notes_path, encoding="utf-8").read() if os.path.isfile(notes_path) else ""

    zip_path = make_zip(version)
    asset_name = os.path.basename(zip_path)
    digest = sha256(zip_path)
    log(f"SHA256 {digest}")

    # 说明里如果写了校验段，自动替换成实际值
    if "SHA256：" in body:
        body = body.replace(
            body.split("SHA256：")[1].splitlines()[0], digest
        )

    tok = token()
    draft = "--draft" in sys.argv
    try:
        rel = api(f"{API}/releases/tags/{tag}", tok=tok)
        log(f"复用已有 Release {tag}")
        rel = api(f"{API}/releases/{rel['id']}",
                  json.dumps({"body": body, "draft": draft}).encode(),
                  "PATCH", tok=tok)
    except Exception:
        rel = api(f"{API}/releases", json.dumps({
            "tag_name": tag, "name": f"{tag} 版本", "body": body,
            "draft": draft, "prerelease": False,
        }).encode(), "POST", tok=tok)
        log(f"已创建 Release {tag}")

    for a in rel.get("assets", []):
        if a["name"] == asset_name:
            api(f"{API}/releases/assets/{a['id']}", method="DELETE", tok=tok)
            log(f"删除旧附件 {asset_name}")

    size = os.path.getsize(zip_path)
    log(f"上传 {asset_name}（{size / 1024 / 1024:.0f} MB）…")
    t0 = time.time()
    with open(zip_path, "rb") as f:
        data = f.read()
    asset = api(f"{rel['upload_url'].split('{')[0]}?name={asset_name}", data,
                "POST", "application/octet-stream", tok)
    dt = time.time() - t0
    log(f"上传完成 {dt:.0f}s（{size / 1024 / 1024 / dt:.1f} MB/s）")
    log(f"附件 state={asset['state']} size={asset['size']}")
    log(f"页面 {rel['html_url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

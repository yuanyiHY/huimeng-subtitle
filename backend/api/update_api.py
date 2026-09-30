"""应用更新：检查 → 下载（带进度）→ 安装（挂载 DMG、替换 App、重启）。

更新源（config.yaml → update.feed_url）返回 JSON：

    {
      "version": "3.3.0",
      "download_url": "https://…/绘梦subtitle-v3.3.0.dmg",
      "notes": "本次更新内容",
      "size": 598000000
    }

设计取舍：
- 下载在后端做（而不是浏览器），因为打包成 App 后要由后端挂载 DMG、替换自身的
  App 包并重启；浏览器下载拿不到文件也做不了这些。
- 替换运行中的 App 包必须等进程退出，所以安装是"派一个后台脚本、然后退出自己"。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.config import PROJECT_ROOT, load_settings

router = APIRouter()

APP_NAME = "绘梦subtitle"
CHUNK = 1024 * 256

# 下载状态（单例即可：同一时刻只会有一个更新在下载）
STATE: dict[str, Any] = {
    "state": "idle",        # idle | downloading | ready | failed
    "percent": 0.0,
    "received": 0,
    "total": 0,
    "speed": 0.0,           # 字节/秒
    "path": "",
    "filename": "",
    "version": "",
    "url": "",
    "error": "",
    "updated_at": 0.0,
}
_LOCK = threading.Lock()


# --------------------------------------------------------------------------- #
# 版本
# --------------------------------------------------------------------------- #
def _local_version() -> str:
    try:
        return (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() or "0.0.0"
    except Exception:
        return "0.0.0"


def _cmp_versions(a: str, b: str) -> int:
    def parts(v: str) -> list[int]:
        out = []
        for seg in str(v).replace("-", ".").split("."):
            out.append(int(seg) if seg.isdigit() else 0)
        return out or [0]

    pa, pb = parts(a), parts(b)
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return (pa > pb) - (pa < pb)


def _feed_url(request: Request) -> str:
    s = request.app.state.settings
    return str(s.get("update", "feed_url") or "").strip()


def _macos_system_proxies() -> dict[str, str]:
    """读 macOS 系统代理设置（设置 → 网络 → 代理）。

    Python 的 urllib 只认 HTTPS_PROXY 这类环境变量，读不到系统代理 ——
    而国内用户访问 GitHub 基本都要靠代理，不处理的话应用内「检查更新」
    在开着代理的机器上照样失败。
    """
    if sys.platform != "darwin":
        return {}
    try:
        out = subprocess.run(["scutil", "--proxy"], capture_output=True,
                             text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return {}
    prox: dict[str, str] = {}
    for scheme, flag, host, port in (("http", "HTTPEnable", "HTTPProxy", "HTTPPort"),
                                     ("https", "HTTPSEnable", "HTTPSProxy", "HTTPSPort")):
        if not re.search(rf"{flag}\s*:\s*1\b", out):
            continue
        mh = re.search(rf"{host}\s*:\s*(\S+)", out)
        mp = re.search(rf"{port}\s*:\s*(\d+)", out)
        if mh and mp:
            prox[scheme] = f"http://{mh.group(1)}:{mp.group(1)}"
    return prox


def _opener() -> urllib.request.OpenerDirector:
    """能走代理的 opener：环境变量优先，其次 macOS 系统代理。"""
    proxies = urllib.request.getproxies() or _macos_system_proxies()
    return urllib.request.build_opener(urllib.request.ProxyHandler(proxies or {}))


def _cache_dir() -> Path:
    d = Path.home() / "Library" / "Caches" / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _running_bundle() -> Path | None:
    """当前进程所在的 .app 包路径；开发模式（非 App）返回 None。"""
    try:
        exe = Path(sys.executable).resolve()
    except Exception:
        return None
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    return None


def _set(**kw: Any) -> None:
    with _LOCK:
        STATE.update(kw)
        STATE["updated_at"] = time.time()


def _snapshot() -> dict[str, Any]:
    with _LOCK:
        data = dict(STATE)
    data["can_install"] = _running_bundle() is not None
    data["current"] = _local_version()
    return data


# --------------------------------------------------------------------------- #
# 检查更新
# --------------------------------------------------------------------------- #
@router.get("/update/check")
async def check_update(request: Request):
    local = _local_version()
    feed = _feed_url(request)
    if not feed:
        return {"ok": True, "current": local, "configured": False,
                "message": "未配置更新源"}
    # GitHub 在国内网络下偶发 SSL 中断，重试一次能显著降低误报
    data = None
    last: Exception | None = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(feed, headers={"User-Agent": f"huimeng/{local}"})
            with _opener().open(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt == 0:
                time.sleep(1.0)
    if data is None:
        return {"ok": False, "current": local, "configured": True,
                "message": f"检查更新失败：{type(last).__name__}（{str(last)[:70]}）"}

    latest = str(data.get("version") or "").strip()
    available = bool(latest) and _cmp_versions(latest, local) > 0
    return {
        "ok": True,
        "configured": True,
        "current": local,
        "latest": latest or None,
        "update_available": available,
        "download_url": data.get("download_url") or data.get("url") or "",
        "size": data.get("size") or 0,
        "notes": data.get("notes") or "",
        "published_at": data.get("published_at") or "",
        "message": f"发现新版本 v{latest}" if available else "已是最新版本",
    }


# --------------------------------------------------------------------------- #
# 下载（后台线程 + 进度）
# --------------------------------------------------------------------------- #
class DownloadBody(BaseModel):
    url: str = ""
    version: str = ""


def _download_worker(url: str, version: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"huimeng/{_local_version()}"})
        with _opener().open(req, timeout=60) as resp, open(tmp, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or 0)
            received = 0
            started = time.time()
            last_push = 0.0
            _set(state="downloading", percent=0.0, received=0, total=total,
                 speed=0.0, error="", version=version, url=url, filename=dest.name)
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
                received += len(chunk)
                now = time.time()
                if now - last_push >= 0.25:      # 别刷太勤，前端轮询够用
                    last_push = now
                    elapsed = max(0.001, now - started)
                    _set(received=received,
                         percent=round(received / total * 100, 1) if total else 0.0,
                         speed=round(received / elapsed, 0))
        if total and tmp.stat().st_size != total:
            raise RuntimeError(f"下载不完整：{tmp.stat().st_size}/{total} 字节")
        tmp.replace(dest)
        _set(state="ready", percent=100.0, path=str(dest), error="")
    except Exception as exc:  # noqa: BLE001
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        _set(state="failed", error=f"{type(exc).__name__}: {str(exc)[:200]}")


@router.post("/update/download")
async def start_download(body: DownloadBody):
    url = (body.url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="下载地址无效")
    with _LOCK:
        if STATE["state"] == "downloading":
            return {"ok": True, "message": "已经在下载中", **dict(STATE)}
    # 文件名可能是百分号编码（中文名很常见），解码后再落盘
    raw = url.split("?")[0].rstrip("/").split("/")[-1]
    name = urllib.parse.unquote(raw) or f"{APP_NAME}.dmg"
    name = name.replace("/", "_")
    dest = _cache_dir() / name
    dest.unlink(missing_ok=True)
    _set(state="downloading", percent=0.0, received=0, total=0, speed=0.0,
         error="", path="", filename=name, version=body.version, url=url)
    threading.Thread(target=_download_worker, args=(url, body.version, dest),
                     daemon=True, name="update-download").start()
    return {"ok": True, "message": "开始下载"}


@router.get("/update/status")
async def update_status():
    return {"ok": True, **_snapshot()}


# --------------------------------------------------------------------------- #
# 安装：挂载 DMG → 替换 App 包 → 重启
# --------------------------------------------------------------------------- #
def _mount_dmg(dmg: Path) -> tuple[str, str]:
    """挂载 DMG，返回 (挂载点, 里面的 .app 路径)。"""
    out = subprocess.run(["hdiutil", "attach", str(dmg), "-nobrowse", "-readonly"],
                         capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"挂载失败：{out.stderr.strip()[:160]}")
    mount = ""
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[-1].startswith("/Volumes/"):
            mount = parts[-1].strip()
    if not mount:
        raise RuntimeError("挂载成功但找不到挂载点")
    apps = sorted(Path(mount).glob("*.app"))
    if not apps:
        raise RuntimeError("安装包里没有找到 .app")
    return mount, str(apps[0])


def _write_installer(target: Path, source: str, mount: str, dmg: Path) -> Path:
    script = _cache_dir() / "install-update.sh"
    script.write_text(f"""#!/bin/bash
# 由绘梦subtitle 生成的更新脚本：等旧进程退出 → 替换 App → 卸载镜像 → 重新打开
set -u
PID={os.getpid()}
TARGET={json.dumps(str(target), ensure_ascii=False)}
SOURCE={json.dumps(source, ensure_ascii=False)}
MOUNT={json.dumps(mount, ensure_ascii=False)}
DMG={json.dumps(str(dmg), ensure_ascii=False)}
LOG="$HOME/Library/Logs/绘梦subtitle-update.log"
exec >> "$LOG" 2>&1
echo "===== $(date '+%F %T') 开始安装 ====="

# 1) 等旧进程退出（最多 30 秒）
for _ in $(seq 1 60); do
  kill -0 "$PID" 2>/dev/null || break
  sleep 0.5
done
sleep 1

# 2) 替换 App 包（先移到一边，失败还能回滚）
BACKUP="$TARGET.old"
rm -rf "$BACKUP"
if ! mv "$TARGET" "$BACKUP"; then
  echo "移动旧版本失败，放弃更新"
  hdiutil detach "$MOUNT" -quiet
  exit 1
fi
if ! cp -R "$SOURCE" "$TARGET"; then
  echo "复制新版本失败，回滚"
  rm -rf "$TARGET"
  mv "$BACKUP" "$TARGET"
  hdiutil detach "$MOUNT" -quiet
  exit 1
fi
rm -rf "$BACKUP"

# 3) 去掉隔离属性，卸载镜像，打开新版
xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null
codesign --force --deep -s - "$TARGET" >/dev/null 2>&1
hdiutil detach "$MOUNT" -quiet 2>/dev/null
rm -f "$DMG"
echo "安装完成，重新打开…"
open "$TARGET"
""", encoding="utf-8")
    script.chmod(0o755)
    return script


@router.post("/update/install")
async def install_update():
    snap = _snapshot()
    if snap["state"] != "ready" or not snap["path"]:
        raise HTTPException(status_code=400, detail="还没有下载好的安装包")
    dmg = Path(snap["path"])
    if not dmg.exists():
        raise HTTPException(status_code=400, detail="安装包文件不存在，请重新下载")
    target = _running_bundle()
    if target is None:
        raise HTTPException(status_code=400,
                            detail="当前是开发模式（不是 App 包），请手动安装 DMG")
    try:
        mount, source = _mount_dmg(dmg)
    except Exception as exc:  # noqa: BLE001
        _set(state="failed", error=str(exc)[:200])
        raise HTTPException(status_code=500, detail=str(exc)[:200])
    try:
        script = _write_installer(target, source, mount, dmg)
        subprocess.Popen(["/bin/bash", str(script)], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:  # noqa: BLE001
        subprocess.run(["hdiutil", "detach", mount, "-quiet"], capture_output=True)
        _set(state="failed", error=str(exc)[:200])
        raise HTTPException(status_code=500, detail=f"启动安装脚本失败：{exc}")
    _set(state="installing")
    return {"ok": True, "message": "正在安装，应用即将自动重启"}


@router.post("/app/quit")
async def quit_app():
    """退出应用（安装脚本会等这个进程消失后再替换 App 包）。"""
    def _bye() -> None:
        time.sleep(0.6)
        os._exit(0)

    threading.Thread(target=_bye, daemon=True).start()
    return {"ok": True, "message": "应用即将退出"}

"""Storage settings API: get / save recording & archive directories, and pop a
native macOS folder picker (osascript `choose folder`) so the user can select a
folder instead of typing a path."""
from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.config import env_file_path, load_settings

router = APIRouter()

ENV_PATH = env_file_path()


class StorageBody(BaseModel):
    recordings_dir: str = ""
    archives_dir: str = ""


def _set_env_var(key: str, value: str) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    out: list = []
    found = False
    for line in lines:
        if line.startswith(key + "="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


@router.get("/storage")
async def get_storage(request: Request):
    s = request.app.state.settings
    return {"ok": True,
            "recordings_dir": str(s.recordings_dir),
            "archives_dir": str(s.archives_dir)}


@router.post("/storage/pick")
async def pick_folder():
    """Pop a native macOS folder chooser and return the selected path."""
    try:
        proc = subprocess.run(
            ["osascript", "-e",
             'POSIX path of (choose folder with prompt "选择保存文件夹")'],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "cancelled": True, "path": None}
    path = proc.stdout.strip()
    if proc.returncode != 0 or not path:
        return {"ok": False, "cancelled": True, "path": None}
    return {"ok": True, "cancelled": False, "path": path}


@router.post("/storage")
async def save_storage(request: Request, body: StorageBody):
    rec = body.recordings_dir.strip()
    arch = body.archives_dir.strip()
    if rec:
        _set_env_var("RECORDINGS_DIR", rec)
    if arch:
        _set_env_var("ARCHIVES_DIR", arch)
    # Hot-swap settings so new recordings/archives use the new dirs immediately.
    settings = load_settings()
    request.app.state.settings = settings
    return {"ok": True, "message": "已保存，立即生效",
            "recordings_dir": str(settings.recordings_dir),
            "archives_dir": str(settings.archives_dir)}

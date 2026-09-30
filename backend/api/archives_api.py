"""Course archives API: save / list / read / delete course summaries."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.utils.security import is_safe_filename, safe_path_join

router = APIRouter()


class ArchiveBody(BaseModel):
    title: str = ""
    body: str = ""
    transcript: str = ""


def _dir(request: Request) -> Path:
    d = Path(request.app.state.settings.archives_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("/archives")
async def list_archives(request: Request):
    d = _dir(request)
    items = []
    for f in sorted(d.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            items.append({
                "name": f.stem,
                "title": data.get("title") or f.stem,
                "created": data.get("created", ""),
            })
        except Exception:
            continue
    return {"ok": True, "archives": items}


@router.post("/archives")
async def save_archive(request: Request, body: ArchiveBody):
    """
    Save a new archive with unique ID and exclusive creation.
    
    Uses UUID to prevent same-second collisions, and exclusive file creation
    to prevent race conditions.
    """
    d = _dir(request)
    
    # Generate unique ID: timestamp + short UUID
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    unique_id = str(uuid.uuid4())[:8]
    name = f"{timestamp}_{unique_id}"
    
    data = {
        "title": body.title.strip() or f"课程 {timestamp}",
        "body": body.body,
        "transcript": body.transcript,
        "created": timestamp,
        "id": name,
    }
    
    file_path = d / f"{name}.json"
    
    # Use exclusive creation ("x" mode) to prevent race conditions
    try:
        with file_path.open("x", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except FileExistsError:
        # Extremely unlikely with UUID, but handle it
        raise HTTPException(status_code=409, detail="归档ID冲突，请重试")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")
    
    return {"ok": True, "name": name, "message": "已归档"}


@router.get("/archives/{name}")
async def get_archive(request: Request, name: str):
    """
    Get an archive by name (with path validation).
    """
    # Validate filename to prevent path traversal
    if not is_safe_filename(name):
        raise HTTPException(status_code=400, detail="归档名称无效")
    
    d = _dir(request)
    
    try:
        f = safe_path_join(d, f"{name}.json")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not f.exists():
        raise HTTPException(status_code=404, detail="归档不存在")
    
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="归档文件损坏")
    
    return {"ok": True, "name": name, **data}


@router.delete("/archives/{name}")
async def delete_archive(request: Request, name: str):
    """
    Delete an archive by name (with path validation).
    """
    # Validate filename to prevent path traversal
    if not is_safe_filename(name):
        raise HTTPException(status_code=400, detail="归档名称无效")
    
    d = _dir(request)
    
    try:
        f = safe_path_join(d, f"{name}.json")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not f.exists():
        raise HTTPException(status_code=404, detail="归档不存在")
    
    try:
        f.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")
    
    return {"ok": True, "message": "已删除"}

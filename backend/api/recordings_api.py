"""Recordings library API: list / rename / delete / subtitles / audio."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.utils.security import is_safe_filename, safe_path_join, sanitize_filename

router = APIRouter()


def _rec_dir(request: Request) -> Path:
    d = Path(request.app.state.settings.recordings_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _base_of(wav_path: Path) -> str:
    return wav_path.stem


@router.get("/recordings")
async def list_recordings(request: Request):
    d = _rec_dir(request)
    items = []
    for wav in sorted(d.glob("*.wav"), reverse=True):
        meta = d / f"{wav.stem}.json"
        subtitles = []
        duration = 0.0
        if meta.exists():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                subtitles = data.get("subtitles", [])
                duration = data.get("duration", 0.0)
            except Exception:
                pass
        items.append({
            "name": wav.stem,
            "size": wav.stat().st_size,
            "duration": round(duration, 1),
            "subtitle_count": len(subtitles),
            "created": wav.stem,
        })
    return {"ok": True, "recordings": items}


@router.get("/recordings/{name}/subtitles")
async def get_subtitles(request: Request, name: str):
    """
    Get subtitles for a recording (with path validation).
    """
    # Validate filename to prevent path traversal
    if not is_safe_filename(name):
        raise HTTPException(status_code=400, detail="录音名称无效")
    
    d = _rec_dir(request)
    
    try:
        meta = safe_path_join(d, f"{name}.json")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not meta.exists():
        return {"ok": True, "subtitles": []}
    
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        return {"ok": True, "subtitles": data.get("subtitles", [])}
    except Exception:
        return {"ok": True, "subtitles": []}


@router.get("/recordings/{name}/audio")
async def get_audio(request: Request, name: str):
    """
    Get audio file for a recording (with path validation).
    """
    # Validate filename to prevent path traversal
    if not is_safe_filename(name):
        raise HTTPException(status_code=400, detail="录音名称无效")
    
    d = _rec_dir(request)
    
    try:
        wav = safe_path_join(d, f"{name}.wav")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not wav.exists():
        raise HTTPException(status_code=404, detail="录音文件不存在")
    
    return FileResponse(str(wav), media_type="audio/wav")


class RenameBody(BaseModel):
    old: str
    new: str


@router.post("/recordings/rename")
async def rename(request: Request, body: RenameBody):
    """
    Rename a recording (with path validation and collision detection).
    
    This operation renames both the .wav and .json files as a transaction.
    If the target name already exists, returns a 409 Conflict error.
    """
    d = _rec_dir(request)
    old, new = body.old.strip(), body.new.strip()
    
    # Basic validation
    if not old or not new or old == new:
        raise HTTPException(status_code=400, detail="名称无效")
    
    # Validate old filename
    if not is_safe_filename(old):
        raise HTTPException(status_code=400, detail="源文件名包含非法字符")
    
    # Sanitize and validate new filename (strip .wav/.json extensions if present)
    try:
        safe_new = sanitize_filename(new, strip_extension=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Check length limit
    if len(safe_new.encode('utf-8')) > 200:
        raise HTTPException(status_code=400, detail="名称过长，请使用不超过 200 字节的名称")
    
    # Validate paths
    try:
        old_wav = safe_path_join(d, f"{old}.wav")
        old_json = safe_path_join(d, f"{old}.json")
        new_wav = safe_path_join(d, f"{safe_new}.wav")
        new_json = safe_path_join(d, f"{safe_new}.json")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Check source exists
    if not old_wav.exists():
        raise HTTPException(status_code=404, detail="源录音文件不存在")
    
    # Check target collision
    if new_wav.exists() or new_json.exists():
        raise HTTPException(
            status_code=409, 
            detail=f"目标名称 '{safe_new}' 已存在，请换一个名字"
        )
    
    # Perform atomic rename (both files must succeed or both fail)
    try:
        # Rename WAV
        old_wav.rename(new_wav)
        
        # Rename JSON if exists
        if old_json.exists():
            try:
                old_json.rename(new_json)
                
                # Update metadata's started_at field
                try:
                    data = json.loads(new_json.read_text(encoding="utf-8"))
                    data["started_at"] = safe_new
                    new_json.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                except Exception:
                    # Metadata update failure is not critical
                    pass
            except Exception as e:
                # Rollback: rename WAV back
                try:
                    new_wav.rename(old_wav)
                except Exception:
                    # Rollback failed - log and notify user
                    raise HTTPException(
                        status_code=500, 
                        detail=f"重命名JSON失败，回滚也失败，请手动检查文件: {e}"
                    )
                raise HTTPException(status_code=500, detail=f"重命名JSON失败，已回滚: {e}")
    except HTTPException:
        raise
    except OSError as e:
        # Handle filesystem errors (e.g., ENAMETOOLONG, permission denied)
        if e.errno == 63:  # ENAMETOOLONG on macOS/BSD
            raise HTTPException(status_code=400, detail="名称过长")
        raise HTTPException(status_code=500, detail=f"重命名失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重命名失败: {e}")
    
    return {"ok": True, "name": safe_new, "message": "已重命名"}


@router.delete("/recordings/{name}")
async def delete(request: Request, name: str):
    """
    Delete a recording (with path validation).
    """
    # Validate filename to prevent path traversal
    if not is_safe_filename(name):
        raise HTTPException(status_code=400, detail="录音名称无效")
    
    d = _rec_dir(request)
    
    try:
        wav = safe_path_join(d, f"{name}.wav")
        meta = safe_path_join(d, f"{name}.json")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Check if recording exists
    if not wav.exists() and not meta.exists():
        raise HTTPException(status_code=404, detail="录音不存在")
    
    # Delete both files
    deleted = False
    try:
        if wav.exists():
            wav.unlink()
            deleted = True
        if meta.exists():
            meta.unlink()
            deleted = True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")
    
    if not deleted:
        raise HTTPException(status_code=404, detail="录音不存在")
    
    return {"ok": True, "message": "已删除"}

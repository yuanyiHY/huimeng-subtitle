"""工作区 API：默认记录、随堂笔记、会议整理的统一存储与后台分析。"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from backend.utils.security import is_safe_filename, safe_path_join

router = APIRouter()
GROUPS = {"default": "默认", "notes": "随堂笔记", "meetings": "会议整理"}


# 深度整理的输出方式
_OUTPUT_RULE = {
    "source": "请用原文语言输出整理结果。",
    "both": ("请用双语对照输出整理结果：每个要点先给译文，紧接一行以「原文：」给出对应原文，"
             "两部分都要完整，不要只输出其中一种。"),
    "target": ("请用译文语言输出整理结果；遇到关键术语、专有名词、人名、产品名、数字与关键决策时，"
               "在译法后面用括号附上原文词段，格式如：术语（original），便于对照查证。"),
}


def _material(data: dict[str, Any], mode: str) -> str:
    """按输出方式组装喂给深度思考模型的材料。

    即使选择「译文为主」，也同时提供原文 —— 模型必须先看到原文，才能在关键处引用原词。
    """
    source = (data.get("transcript") or "").strip()
    target = (data.get("translation") or "").strip()
    if mode == "source" or not target:
        return source
    paired = []
    for item in data.get("timeline") or []:
        s = str(item.get("source") or item.get("ko") or "").strip()
        t = str(item.get("target") or item.get("zh") or "").strip()
        if s or t:
            paired.append(f"原文：{s}\n译文：{t}")
    if paired:
        return "\n\n".join(paired)
    return f"【原文】\n{source}\n\n【译文】\n{target}"


class SessionBody(BaseModel):
    group: Literal["default", "notes", "meetings"] = "default"
    output_mode: Literal["source", "target", "both"] = "target"
    title: str = ""
    source_type: str = "live"
    source_name: str = ""
    recording_name: str = ""
    description: str = ""
    duration: float = 0
    transcript: str = ""
    translation: str = ""
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    quick_summary: str = ""
    analysis: str = ""
    analyze: bool = True


class SettingsBody(BaseModel):
    language: str = "zh-CN"
    microphone: str = "default"
    models: dict[str, Any] = Field(default_factory=dict)


def _root(request: Request) -> Path:
    path = Path(request.app.state.settings.archives_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _group_dir(request: Request, group: str) -> Path:
    if group not in GROUPS:
        raise HTTPException(status_code=400, detail="未知的文件分组")
    path = _root(request) / group
    path.mkdir(parents=True, exist_ok=True)
    return path


def _settings_path(request: Request) -> Path:
    return _root(request) / "workspace-settings.json"


def _read(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _title(body: SessionBody) -> str:
    if body.title.strip():
        return body.title.strip()
    if body.source_name.strip():
        return body.source_name.strip()
    return f"{GROUPS[body.group]} {time.strftime('%Y-%m-%d %H:%M')}"


def _analyze(path: Path, group: str, transcript: str, quick_summary: str,
             output_mode: str = "") -> None:
    data = _read(path)
    mode = output_mode or data.get("output_mode") or "target"
    material = _material(data, mode) or transcript
    try:
        from backend.orchestrator import Orchestrator
        # 这里使用应用创建时已配置的模型设置；失败时仍保留原始材料。
        from backend.config import load_settings
        prompt = (
            "请按随堂笔记规则整理：课程摘要、知识结构、重点、关键词、待办事项。"
            if group == "notes" else
            "请按会议整理规则整理：会议摘要、关键决策、待办事项、参与人任务。"
        )
        result = Orchestrator(load_settings()).summarize(
            material,
            prompt
            + _OUTPUT_RULE.get(mode, _OUTPUT_RULE["target"])
            + ("\n实时快速提示：" + quick_summary if quick_summary else ""),
        )
        data["analysis"] = result.get("text", "")
        data["analysis_engine"] = result.get("engine", "")
        data["status"] = "ready" if result.get("ok") else "failed"
        data["error"] = "" if result.get("ok") else result.get("message", "分析失败")
    except Exception as exc:  # 保留原始记录，避免分析失败造成数据丢失
        data["status"] = "failed"
        data["error"] = str(exc)[:300]
    data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write(path, data)


@router.get("/workspace/summary")
async def summary(request: Request):
    result = {"ok": True, "groups": {}}
    for group, label in GROUPS.items():
        directory = _group_dir(request, group)
        items = []
        for path in sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            data = _read(path)
            if not data:
                continue
            items.append({
                "id": path.stem,
                "group": group,
                "label": label,
                "title": data.get("title", path.stem),
                "created": data.get("created", ""),
                "updated": data.get("updated", data.get("created", "")),
                "status": data.get("status", "ready"),
                "source_type": data.get("source_type", "live"),
                "source_name": data.get("source_name", ""),
                "duration": data.get("duration", 0),
                "error": data.get("error", ""),
            })
        result["groups"][group] = items
    return result


@router.get("/workspace/files/{group}")
async def list_files(request: Request, group: str):
    data = await summary(request)
    return {"ok": True, "group": group, "files": data.get("groups", {}).get(group, [])}


@router.get("/workspace/files/{group}/{file_id}")
async def get_file(request: Request, group: str, file_id: str):
    if not is_safe_filename(file_id):
        raise HTTPException(status_code=400, detail="文件记录名称无效")
    directory = _group_dir(request, group)
    path = safe_path_join(directory, f"{file_id}.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件记录不存在")
    return {"ok": True, "group": group, **_read(path)}


@router.post("/workspace/files", status_code=202)
async def save_file(request: Request, body: SessionBody, background_tasks: BackgroundTasks):
    directory = _group_dir(request, body.group)
    now = time.strftime("%Y-%m-%d_%H-%M-%S")
    file_id = f"{now}_{uuid.uuid4().hex[:8]}"
    path = directory / f"{file_id}.json"
    should_analyze = body.group != "default" and body.analyze
    data = {
        "id": file_id,
        "group": body.group,
        "group_label": GROUPS[body.group],
        "title": _title(body),
        "source_type": body.source_type,
        "source_name": body.source_name,
        "recording_name": body.recording_name,
        "description": body.description,
        "duration": body.duration,
        "transcript": body.transcript,
        "translation": body.translation,
        "timeline": body.timeline,
        "quick_summary": body.quick_summary,
        "output_mode": body.output_mode,
        "analysis": body.analysis,
        "status": "analyzing" if should_analyze else "ready",
        "error": "",
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _write(path, data)
    if should_analyze:
        background_tasks.add_task(_analyze, path, body.group, body.transcript,
                                  body.quick_summary, body.output_mode)
    return {"ok": True, "id": file_id, "group": body.group, "status": data["status"], "message": "已保存，后台分析中" if should_analyze else "已保存"}


@router.post("/workspace/files/{group}/{file_id}/retry")
async def retry_file(request: Request, group: str, file_id: str, background_tasks: BackgroundTasks):
    if not is_safe_filename(file_id):
        raise HTTPException(status_code=400, detail="文件记录名称无效")
    directory = _group_dir(request, group)
    path = safe_path_join(directory, f"{file_id}.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件记录不存在")
    data = _read(path)
    data["status"] = "analyzing"
    data["error"] = ""
    data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write(path, data)
    background_tasks.add_task(_analyze, path, group, data.get("transcript", ""),
                              data.get("quick_summary", ""), data.get("output_mode", "target"))
    return {"ok": True, "status": "analyzing", "message": "已重新加入分析队列"}


@router.delete("/workspace/files/{group}/{file_id}")
async def delete_file(request: Request, group: str, file_id: str):
    if not is_safe_filename(file_id):
        raise HTTPException(status_code=400, detail="文件记录名称无效")
    path = safe_path_join(_group_dir(request, group), f"{file_id}.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件记录不存在")
    path.unlink()
    return {"ok": True, "message": "已删除"}


@router.get("/workspace/settings")
async def get_workspace_settings(request: Request):
    path = _settings_path(request)
    return {"ok": True, **(_read(path) or {"language": "zh-CN", "microphone": "default", "models": {}})}


@router.post("/workspace/settings")
async def save_workspace_settings(request: Request, body: SettingsBody):
    data = body.dict()
    _write(_settings_path(request), data)
    return {"ok": True, "message": "设置已保存", **data}

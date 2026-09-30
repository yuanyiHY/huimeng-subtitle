"""文件转写任务队列 + 导出接口。

上传文件后立刻返回任务 ID，真正的转写在后台线程里跑，前端轮询
``GET /api/tasks`` 显示进度与状态。任务完成后把时间线、原文、译文写进
对应分组（默认 / 随堂笔记 / 会议整理），非默认分组会继续调用深度思考
模型做后台整理。
"""
from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from backend.utils.security import is_safe_filename, sanitize_filename

router = APIRouter()

GROUPS = {"default": "默认", "notes": "随堂笔记", "meetings": "会议整理"}
AUDIO_EXT = {"wav", "flac", "mp3", "ogg", "m4a", "aac", "mp4", "mov", "mkv", "webm", "avi"}
TEXT_EXT = {"txt", "md", "srt", "vtt"}
DOC_EXT = {"pdf", "docx"}

TASKS: dict[str, dict[str, Any]] = {}
_QUEUE: "queue.Queue[str]" = queue.Queue()
_LOCK = threading.Lock()
_WORKER: threading.Thread | None = None
_STATE: Any = None


# --------------------------------------------------------------------------- #
# 存储
# --------------------------------------------------------------------------- #
def _root(state) -> Path:
    path = Path(state.settings.archives_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _task_dir(state) -> Path:
    path = _root(state) / "_tasks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _uploads_dir(state) -> Path:
    path = _root(state) / "_uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _persist(task: dict[str, Any]) -> None:
    try:
        path = _task_dir(_STATE) / f"{task['id']}.json"
        path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _load_all(state) -> None:
    try:
        for path in _task_dir(state).glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("status") in ("running", "waiting"):
                data["status"] = "failed"
                data["stage"] = "已中断"
                data["message"] = "应用重启导致任务中断，可点击重试"
            TASKS[data["id"]] = data
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 工作线程
# --------------------------------------------------------------------------- #
def _ensure_worker() -> None:
    global _WORKER
    with _LOCK:
        if _WORKER is None or not _WORKER.is_alive():
            _WORKER = threading.Thread(target=_loop, daemon=True, name="transcribe-worker")
            _WORKER.start()


def _loop() -> None:
    while True:
        task_id = _QUEUE.get()
        try:
            _run(task_id)
        except Exception as exc:  # noqa: BLE001 - 任务失败不能拖垮工作线程
            _update(task_id, status="failed", stage="失败", message=str(exc)[:300])
        finally:
            _QUEUE.task_done()


def _update(task_id: str, **fields: Any) -> None:
    task = TASKS.get(task_id)
    if not task:
        return
    task.update(fields)
    task["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _persist(task)


def _public(task: dict[str, Any], with_segments: bool = False) -> dict[str, Any]:
    data = {k: v for k, v in task.items() if k not in ("stored",)}
    if not with_segments:
        data.pop("segments", None)
    return data


def _kind_of(ext: str) -> str:
    if ext in ("mp3", "m4a", "wav", "aac", "flac", "ogg"):
        return "audio"
    if ext in ("mp4", "mov", "mkv", "webm", "avi"):
        return "video"
    if ext in ("pdf", "doc", "docx", "txt", "md", "rtf"):
        return "doc"
    return "other"


def _read_document(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext in TEXT_EXT:
        return path.read_text(encoding="utf-8", errors="ignore")
    if ext == "docx":
        import docx  # python-docx
        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    if ext == "pdf":
        from pypdf import PdfReader
        return "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
    raise RuntimeError(f"暂不支持直接解析 .{ext} 文档，请先转为文本或音频")


def _duration_of(path: Path) -> float:
    try:
        import soundfile as sf
        return float(sf.info(str(path)).duration)
    except Exception:
        return 0.0


def _run(task_id: str) -> None:
    state = _STATE
    task = TASKS.get(task_id)
    if not task or not state:
        return
    src = task.get("src_lang") or "auto"
    tgt = task.get("tgt_lang") or "zh"
    group = task.get("group") or "default"
    path = Path(task["stored"])
    ext = path.suffix.lower().lstrip(".")
    segments: list[dict[str, Any]] = []
    duration = 0.0

    _update(task_id, status="running", stage="转写中", progress=8, message="")

    try:
        if ext in TEXT_EXT or ext in DOC_EXT:
            text = _read_document(path)
            chunks = [c.strip() for c in text.replace("\r", "").split("\n") if c.strip()]
            segments = [{"start": 0.0, "end": 0.0, "text": c} for c in chunks]
        else:
            asr = state.asr_engine
            if not asr.available():
                raise RuntimeError("本地语音识别未就绪（mlx-whisper 缺失），无法转写音视频")
            wav_path = path
            if ext not in ("wav", "flac", "mp3", "ogg"):
                from backend.utils.audio import decode_to_wav
                wav_path = decode_to_wav(path, _uploads_dir(state) / f"{task_id}.wav")
            duration = _duration_of(wav_path)
            _update(task_id, progress=25, stage="转写中")
            segs = asr.transcribe_file(str(wav_path), "auto" if src == "auto" else src)
            segments = [{"start": float(s.start), "end": float(s.end), "text": s.text} for s in segs]
    except Exception as exc:  # noqa: BLE001
        from backend.errors import classify_exception, humanize
        code = classify_exception(exc)
        _update(task_id, status="failed", stage="转写失败", progress=100,
                message=f"{humanize(code)}：{str(exc)[:200]}")
        return

    text = " ".join(s["text"] for s in segments).strip()
    if not text:
        _update(task_id, status="failed", stage="转写失败", progress=100,
                message="没有识别到有效内容，请确认音频包含人声")
        return

    _update(task_id, progress=62, stage="翻译中", text=text[:4000])

    if tgt:
        try:
            mt = state.mt_engine
            if mt.available():
                batch = [s["text"] for s in segments]
                out: list[str] = []
                for i in range(0, len(batch), 20):
                    out.extend(mt.translate(batch[i:i + 20], "auto" if src == "auto" else src, tgt))
                for i, seg in enumerate(segments):
                    seg["zh"] = out[i] if i < len(out) else ""
        except Exception as exc:  # noqa: BLE001 - 翻译失败仍保留原文
            print(f"[tasks] 翻译失败（保留原文）: {exc}", flush=True)

    _update(task_id, progress=80, stage="整理中" if group != "default" else "保存中",
            segments=segments, duration=round(duration, 1))

    record_id = _save_record(state, task, group, segments, duration)
    _update(task_id, file_id=record_id, group=group, progress=100,
            status="done", stage="转写完成", segments=segments,
            message=f"已归档到「{GROUPS.get(group, group)}」")


def _save_record(state, task: dict[str, Any], group: str, segments: list[dict[str, Any]],
                 duration: float) -> str:
    directory = _root(state) / group
    directory.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%d_%H-%M-%S")
    record_id = f"{now}_{uuid.uuid4().hex[:8]}"
    should_analyze = group != "default"
    title = Path(task["name"]).stem or task["name"]
    data = {
        "id": record_id,
        "group": group,
        "group_label": GROUPS.get(group, group),
        "title": title,
        "source_type": "transcribe",
        "source_name": task["name"],
        "recording_name": "",
        "description": task.get("description", ""),
        "duration": round(duration, 1),
        "transcript": "\n".join(s["text"] for s in segments),
        "translation": "\n".join(s.get("zh", "") for s in segments),
        "timeline": [
            {"start": s["start"], "end": s["end"], "source": s["text"], "target": s.get("zh", "")}
            for s in segments
        ],
        "quick_summary": "",
        "output_mode": task.get("output_mode", "target"),
        "analysis": "",
        "status": "analyzing" if should_analyze else "ready",
        "error": "",
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    path = directory / f"{record_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if should_analyze:
        try:
            from backend.api.workspace_api import _analyze
            _update(task["id"], stage="后台整理中")
            _analyze(path, group, data["transcript"], "", task.get("output_mode", "target"))
        except Exception as exc:  # noqa: BLE001 - 分析失败不影响转写结果
            print(f"[tasks] 后台整理失败: {exc}", flush=True)
    return record_id


# --------------------------------------------------------------------------- #
# 接口
# --------------------------------------------------------------------------- #
@router.get("/tasks")
async def list_tasks(request: Request):
    global _STATE
    _STATE = request.app.state
    if not TASKS:
        _load_all(request.app.state)
    items = sorted(TASKS.values(), key=lambda t: t.get("created", ""), reverse=True)
    return {"ok": True, "tasks": [_public(t) for t in items]}


@router.get("/tasks/{task_id}")
async def get_task(request: Request, task_id: str):
    global _STATE
    _STATE = request.app.state
    if not is_safe_filename(task_id) or task_id not in TASKS:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True, **_public(TASKS[task_id], with_segments=True)}


@router.post("/tasks")
async def create_task(
    request: Request,
    file: UploadFile = File(...),
    group: str = Form("default"),
    src_lang: str = Form("auto"),
    tgt_lang: str = Form("zh"),
    diarization: str = Form("0"),
    timeline: str = Form("1"),
    vocab: str = Form("1"),
    output_mode: str = Form("target"),  # source（原文）| target（译文为主）| both（双语）
):
    global _STATE
    state = request.app.state
    _STATE = state
    if group not in GROUPS:
        raise HTTPException(status_code=400, detail="未知的文件分组")
    name = Path(file.filename or "未命名文件").name
    ext = Path(name).suffix.lower().lstrip(".")
    task_id = uuid.uuid4().hex[:12]
    stored = _uploads_dir(state) / f"{task_id}_{name}"
    payload = await file.read()
    stored.write_bytes(payload)

    task = {
        "id": task_id,
        "name": name,
        "ext": ext,
        "kind": _kind_of(ext),
        "size": len(payload),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "waiting",
        "stage": "等待转写",
        "progress": 3,
        "group": group,
        "src_lang": src_lang,
        "tgt_lang": tgt_lang,
        "options": {"diarization": diarization == "1", "timeline": timeline == "1", "vocab": vocab == "1"},
        "output_mode": output_mode if output_mode in ("source", "target", "both") else "target",
        "text": "",
        "segments": [],
        "duration": 0,
        "file_id": "",
        "message": "",
        "stored": str(stored),
    }
    TASKS[task_id] = task
    _persist(task)
    _ensure_worker()
    _QUEUE.put(task_id)
    return {"ok": True, "id": task_id, "task": _public(task), "message": "已加入转写队列"}


@router.post("/tasks/{task_id}/retry")
async def retry_task(request: Request, task_id: str):
    global _STATE
    _STATE = request.app.state
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not Path(task["stored"]).exists():
        raise HTTPException(status_code=400, detail="原始文件已被清理，请重新上传")
    _update(task_id, status="waiting", stage="等待转写", progress=3, message="")
    _ensure_worker()
    _QUEUE.put(task_id)
    return {"ok": True, "message": "已重新加入转写队列"}


@router.delete("/tasks/{task_id}")
async def delete_task(request: Request, task_id: str):
    global _STATE
    _STATE = request.app.state
    task = TASKS.pop(task_id, None)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        Path(task["stored"]).unlink(missing_ok=True)
        (_task_dir(request.app.state) / f"{task_id}.json").unlink(missing_ok=True)
    except Exception:
        pass
    return {"ok": True, "message": "已删除任务"}


class ExportBody(BaseModel):
    filename: str = ""
    content: str = ""


@router.post("/export")
async def export_file(body: ExportBody):
    """把导出的文本/Markdown/SRT 写到 ~/Downloads，返回真实路径。"""
    name = sanitize_filename(body.filename or f"绘梦subtitle导出-{int(time.time())}.txt")
    target_dir = Path.home() / "Downloads"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / name
    index = 1
    while path.exists():
        path = target_dir / f"{Path(name).stem}-{index}{Path(name).suffix}"
        index += 1
    try:
        path.write_text(body.content, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"导出失败：{exc}")
    return {"ok": True, "path": str(path), "message": "已导出"}

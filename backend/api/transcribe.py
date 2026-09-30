"""Transcription API: /api/transcribe and one-stop /api/full."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, Form, Request, UploadFile

from backend.asr.base import EngineUnavailable
from backend.errors import ErrorCode, api_error
from backend.utils.audio import decode_to_wav

router = APIRouter()


def _segments_to_dict(segments) -> List[dict]:
    return [
        {"start": s.start, "end": s.end, "text": s.text}
        for s in segments
    ]


def _transcribe_request(request: Request, wav_path: str, language: str):
    return request.app.state.asr_engine.transcribe_file(wav_path, language)


@router.post("/transcribe")
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form("ko"),
):
    engine = request.app.state.asr_engine
    if not engine.available():
        return api_error(
            ErrorCode.ASR_UNAVAILABLE,
            "本地语音识别未就绪（mlx-whisper 缺失）",
            hint="在设置页下载语音识别模型，或安装 requirements-asr.txt 依赖",
            engine=engine.name, degraded=True, text="", segments=[],
        )
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(await file.read())
        wav_path = tmp.name
    try:
        segments = _transcribe_request(request, wav_path, language)
    except EngineUnavailable as exc:
        return api_error(
            ErrorCode.ENGINE_UNAVAILABLE, str(exc),
            engine=engine.name, degraded=True, text="", segments=[],
        )
    finally:
        Path(wav_path).unlink(missing_ok=True)
    return {
        "ok": True, "engine": engine.name, "degraded": False,
        "text": " ".join(s.text for s in segments),
        "segments": _segments_to_dict(segments),
    }


@router.post("/full")
async def full(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form("ko"),
    with_summary: bool = Form(False),
):
    trans_result = await transcribe(request, file, language)
    if not trans_result.get("ok"):
        return trans_result
    segments = trans_result.get("segments", [])
    # Pair each segment with a translation via the MT engine.
    mt = request.app.state.mt_engine
    texts = [s["text"] for s in segments]
    zh = mt.translate(texts) if mt.available() else ["" for _ in texts]
    enriched = [
        {**s, "zh": zh[i] if i < len(zh) else ""}
        for i, s in enumerate(segments)
    ]
    summary = None
    if with_summary:
        from backend.orchestrator import get_orchestrator
        source_text = trans_result.get("text", "")
        summary = request.app.state.orchestrator.summarize(source_text)
    return {
        "ok": True, "engine": trans_result.get("engine", ""),
        "segments": enriched,
        "summary": summary,
    }

"""Translation API: POST /api/translate with explicit engine override."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class TranslateRequest(BaseModel):
    texts: List[str]
    src: str = "ko"
    tgt: str = "zh"
    engine: Optional[str] = None  # auto | local-ct2 | local-nllb | local-qwen | cloud


@router.post("/translate")
async def translate(request: Request, body: TranslateRequest):
    mt = request.app.state.mt_engine
    if not mt.available():
        from backend.errors import ErrorCode, api_error
        return api_error(
            ErrorCode.MT_UNAVAILABLE, "翻译引擎不可用（未安装依赖或未配置云端）",
            engine=mt.name, degraded=True,
            translations=["" for _ in body.texts],
        )
    try:
        translations = mt.translate(body.texts, body.src, body.tgt)
    except Exception as exc:  # pragma: no cover
        from backend.errors import ErrorCode, api_error, classify_exception, humanize
        return api_error(
            classify_exception(exc), f"{humanize(classify_exception(exc))}: {str(exc)[:120]}",
            engine=mt.name, degraded=True,
            translations=["" for _ in body.texts],
        )
    return {"ok": True, "engine": mt.name, "degraded": False,
            "translations": translations}

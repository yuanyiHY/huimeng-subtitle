"""Model manager API: /api/models/*."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class IdBody(BaseModel):
    id: str


class CheckBody(BaseModel):
    transcript: str = ""
    instruction: str = ""


@router.get("/models")
async def models(request: Request):
    return {"ok": True, "models": request.app.state.model_manager.list_models()}


@router.post("/models/download")
async def download(request: Request, body: IdBody):
    return request.app.state.model_manager.start_download(body.id)


@router.post("/models/cancel")
async def cancel(request: Request, body: IdBody):
    return request.app.state.model_manager.cancel_download(body.id)


@router.delete("/models/{mid}")
async def delete(request: Request, mid: str):
    return request.app.state.model_manager.delete_model(mid)


@router.get("/models/progress")
async def progress(request: Request):
    return {"ok": True, "progress": request.app.state.model_manager.progress()}


@router.post("/models/verify")
async def verify(request: Request, body: IdBody):
    """完整验证：先校验文件完整性（大小/哈希），再做真实推理。"""
    mid = body.id
    mgr = request.app.state.model_manager
    integrity = mgr.verify_model(mid)
    if not integrity.get("ok"):
        detail = "；".join(integrity.get("problems") or []) or integrity.get("message", "")
        return {"ok": False, "stage": "integrity",
                "message": f"完整性校验未通过：{detail}",
                "problems": integrity.get("problems", [])}
    import time
    if mid == "whisper":
        import numpy as np
        audio = np.sin(2 * np.pi * 440 * np.arange(16000) / 16000).astype(np.float32)
        t0 = time.time()
        try:
            segs = request.app.state.asr_engine.transcribe_array(audio, "ko")
            dt = time.time() - t0
            return {"ok": True, "message": f"完整性 + 推理验证通过（{dt:.1f}s），模型可用"}
        except Exception as exc:
            return {"ok": False, "stage": "inference", "message": f"验证失败：{str(exc)[:150]}"}
    if mid == "nllb":
        from backend.mt.nllb_engine import NLLBEngine
        eng = NLLBEngine(models_dir=str(request.app.state.settings.models_dir))
        t0 = time.time()
        try:
            out = eng.translate(["안녕하세요"])
            dt = time.time() - t0
            if out and out[0]:
                return {"ok": True, "message": f"完整性 + 翻译验证通过（{dt:.1f}s）：{out[0]}"}
            return {"ok": False, "stage": "inference", "message": "翻译返回空（模型文件可能不完整）"}
        except Exception as exc:
            return {"ok": False, "stage": "inference", "message": f"验证失败：{str(exc)[:150]}"}
    if mid == "qwen":
        from backend.mt.mlx_llm_engine import MLXLLMEngine
        eng = MLXLLMEngine()
        try:
            out = eng.translate(["안녕하세요"])
            if out and out[0]:
                return {"ok": True, "message": f"完整性 + 推理验证通过：{out[0]}"}
            return {"ok": False, "stage": "inference", "message": "翻译返回空（模型文件可能不完整）"}
        except Exception as exc:
            return {"ok": False, "stage": "inference", "message": f"验证失败：{str(exc)[:150]}"}
    return {"ok": False, "message": "未知模型"}


@router.post("/orchestrator/check")
async def check(request: Request):
    return request.app.state.orchestrator.check_translation()


@router.post("/orchestrator/check_main")
async def check_main(request: Request):
    return request.app.state.orchestrator.check_main()


@router.post("/orchestrator/check_light")
async def check_light(request: Request):
    return request.app.state.orchestrator.check_light()


@router.post("/orchestrator/summarize")
async def summarize(request: Request, body: CheckBody):
    return request.app.state.orchestrator.summarize(body.transcript, body.instruction)

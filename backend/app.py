"""FastAPI app assembly for 绘梦subtitle.

Wires settings, engines, model manager and orchestrator onto app.state, mounts
the API routers and serves the frontend from /frontend.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import config as cfg
from backend.api import archives_api, coach, config_api, models_api, profiles_api, recordings_api, storage_api, stream, tasks_api, transcribe, translate, update_api, workspace_api
from backend.live_capture import MicMonitor, NativeCapture, router as capture_router
from backend.asr.api_engine import APIAudioEngine
from backend.asr.mlx_engine import MLXWhisperEngine
from backend.models.manager import ModelManager
from backend.mt.ct2_engine import CT2Engine
from backend.mt.mlx_llm_engine import MLXLLMEngine
from backend.mt.nllb_engine import NLLBEngine
from backend.mt.openai_engine import OpenAIMTEngine
from backend.orchestrator import Orchestrator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def create_app(settings_override: dict | None = None) -> FastAPI:
    settings = cfg.load_settings(settings_override)
    app = FastAPI(title="绘梦subtitle", version="3.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Engines & managers on app.state ---
    mt_engine = _build_mt_engine(settings)
    app.state.settings = settings
    app.state.asr_engine = MLXWhisperEngine(
        model=settings.asr_model, language=settings.asr_language,
        models_dir=str(settings.models_dir),
    )
    # Reserve cloud ASR slot (currently unavailable).
    app.state.asr_api_engine = APIAudioEngine()
    app.state.mt_engine = mt_engine
    app.state.model_manager = ModelManager(
        settings.models_dir, settings.recordings_dir
    )
    app.state.orchestrator = Orchestrator(settings)
    app.state.capture = NativeCapture()
    app.state.monitor = MicMonitor()

    # --- Routers ---
    app.include_router(transcribe.router, prefix="/api")
    app.include_router(translate.router, prefix="/api")
    app.include_router(stream.router, prefix="/api")
    app.include_router(models_api.router, prefix="/api")
    app.include_router(config_api.router, prefix="/api")
    app.include_router(recordings_api.router, prefix="/api")
    app.include_router(archives_api.router, prefix="/api")
    app.include_router(storage_api.router, prefix="/api")
    app.include_router(profiles_api.router, prefix="/api")
    app.include_router(coach.router, prefix="/api")
    app.include_router(update_api.router, prefix="/api")
    app.include_router(workspace_api.router, prefix="/api")
    app.include_router(tasks_api.router, prefix="/api")
    app.include_router(capture_router, prefix="/api")

    # --- Static frontend ---
    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def index():
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"ok": True, "message": "Frontend not built yet; see /docs for API."}

    def _version() -> str:
        try:
            return (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    @app.get("/api/health")
    async def health():
        import os as _os
        return {
            "ok": True,
            "status": "running",
            "version": _version(),
            "window_mode": _os.environ.get("IRT_WINDOW_MODE") == "1",
            "engine_status": _engine_status(app.state),
        }

    # --- 统一错误响应：后端吐 code，前端 error-handler.js 翻人话 ---
    @app.exception_handler(HTTPException)
    async def _http_exception(_request, exc: HTTPException):
        from backend.errors import ErrorCode, api_error
        code = ErrorCode.INTERNAL if exc.status_code >= 500 else ErrorCode.INVALID_ARGUMENT
        return JSONResponse(status_code=exc.status_code,
                            content=api_error(code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def _unhandled_exception(_request, exc: Exception):
        from backend.errors import api_error, classify_exception, humanize
        code = classify_exception(exc)
        return JSONResponse(
            status_code=500,
            content=api_error(code, humanize(code), detail=str(exc)[:200]),
        )

    # translate the engine is available based on deps/override
    return app


def _build_mt_engine(settings: cfg.Settings):
    engine = settings.mt_engine
    if engine == "cloud":
        return OpenAIMTEngine(
            settings.mt_cloud_base_url, settings.mt_cloud_api_key,
            settings.mt_cloud_model, timeout=settings.get("mt", "cloud", "timeout", default=15),
        )
    if engine == "local-qwen":
        return MLXLLMEngine(settings.mt_local_qwen_model)
    if engine == "local-ct2":
        return CT2Engine(str(settings.models_dir))
    if engine == "local-nllb":
        return NLLBEngine(settings.mt_local_model, settings.mt_local_int8,
                          models_dir=str(settings.models_dir))
    # auto: prefer cloud if configured, then CT2 (fast local), then NLLB
    if settings.mt_cloud_base_url and settings.mt_cloud_model:
        return OpenAIMTEngine(
            settings.mt_cloud_base_url, settings.mt_cloud_api_key,
            settings.mt_cloud_model, timeout=settings.get("mt", "cloud", "timeout", default=15),
        )
    ct2 = CT2Engine(str(settings.models_dir))
    if ct2.available():
        return ct2
    return NLLBEngine(settings.mt_local_model, settings.mt_local_int8,
                      models_dir=str(settings.models_dir))


def _engine_status(state) -> dict:
    return {
        "asr": state.asr_engine.name,
        "asr_available": state.asr_engine.available(),
        "mt": state.mt_engine.name,
        "mt_available": state.mt_engine.available(),
    }

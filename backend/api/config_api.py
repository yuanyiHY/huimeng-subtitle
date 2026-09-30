"""Cloud config API: GET /api/config and POST /api/config.

Allows the Settings page to view/edit MT / Main model endpoints, persist them
to .env, and hot-swap the engines without restarting.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.config import env_file_path, load_settings

router = APIRouter()

ENV_PATH = env_file_path()


class CloudConfig(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class ConfigBody(BaseModel):
    mt: CloudConfig = CloudConfig()
    main: CloudConfig = CloudConfig()


def _read_env() -> dict:
    data: dict = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
    return data


def _write_env(mt: CloudConfig, main: CloudConfig) -> None:
    old = _read_env()
    # Blank key keeps the existing one.
    mt_key = mt.api_key.strip() or old.get("MT_API_KEY", "")
    main_key = main.api_key.strip() or old.get("MAIN_API_KEY", "")
    content = f"""# 绘梦subtitle - 云端配置（可在设置页修改）

# 翻译模型（OpenAI 兼容；模型名含 mt 按翻译专用模型传参）
MT_BASE_URL={mt.base_url.strip()}
MT_API_KEY={mt_key}
MT_MODEL={mt.model.strip()}

# 主模型（会议整理：摘要/提纲/复习题）
MAIN_BASE_URL={main.base_url.strip()}
MAIN_API_KEY={main_key}
MAIN_MODEL={main.model.strip()}
"""
    ENV_PATH.write_text(content, encoding="utf-8")


@router.get("/config")
async def get_config(request: Request):
    s = request.app.state.settings
    return {
        "ok": True,
        "mt": {
            "base_url": s.mt_cloud_base_url or "",
            "model": s.mt_cloud_model or "",
            "has_key": bool(s.mt_cloud_api_key),
        },
        "main": {
            "base_url": s.main_base_url or "",
            "model": s.main_model or "",
            "has_key": bool(s.main_api_key),
        },
    }


@router.post("/config")
async def save_config(request: Request, body: ConfigBody):
    _write_env(body.mt, body.main)
    # Hot-swap engines
    settings = load_settings()
    request.app.state.settings = settings
    from backend.app import _build_mt_engine
    from backend.orchestrator import Orchestrator
    request.app.state.mt_engine = _build_mt_engine(settings)
    request.app.state.orchestrator = Orchestrator(settings)
    return {"ok": True, "message": "已保存并立即生效"}

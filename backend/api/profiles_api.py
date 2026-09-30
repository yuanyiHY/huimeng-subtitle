"""Model profiles API: manage multiple cloud model profiles (MT + Main),
switch the active one, and switch the MT engine. Persisted to profiles.json in
the user data dir; the active profile is synced into .env so the existing
settings-driven engine wiring keeps working."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class Profile(BaseModel):
    name: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    thinking: str = ""  # off（关思考）| ""（标准）| deep（深度思考）


class ProfilesBody(BaseModel):
    mt: list[Profile] = []
    main: list[Profile] = []
    light: list[Profile] = []
    mt_active: str = ""
    main_active: str = ""
    light_active: str = ""
    mt_engine: str = "auto"
    live_model: str = ""   # 实时同传模型（百炼 WebSocket 接口）


def _profiles_path(request: Request) -> Path:
    return Path(request.app.state.settings.models_dir).parent / "profiles.json"


def _env_path() -> Path:
    from backend.config import env_file_path
    return env_file_path()


def _set_env(key: str, value: str) -> None:
    env = _env_path()
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    out, found = [], False
    for line in lines:
        if line.startswith(key + "="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    env.write_text("\n".join(out) + "\n", encoding="utf-8")


def _load(request: Request) -> dict:
    p = _profiles_path(request)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            # 兼容旧版 profiles.json（只有 mt / main 两组、没有思考强度字段）
            for key, default_thinking in (("mt", "off"), ("main", "deep"), ("light", "off")):
                data.setdefault(key, [])
                for profile in data[key]:
                    profile.setdefault("thinking", default_thinking)
            for key in ("mt_active", "main_active", "light_active"):
                data.setdefault(key, "")
            data.setdefault("mt_engine", "auto")
            data.setdefault("live_model", "")
            return data
        except Exception:
            pass
    # Migrate from .env on first run.
    s = request.app.state.settings
    mt = []
    if s.mt_cloud_base_url and s.mt_cloud_model:
        mt.append({"name": s.mt_cloud_model, "base_url": s.mt_cloud_base_url,
                   "api_key": s.mt_cloud_api_key or "", "model": s.mt_cloud_model,
                   "thinking": s.mt_thinking})
    main = []
    if s.main_base_url and s.main_model:
        main.append({"name": s.main_model, "base_url": s.main_base_url,
                     "api_key": s.main_api_key or "", "model": s.main_model,
                     "thinking": s.main_thinking})
    light = []
    if s.light_base_url and s.light_model:
        light.append({"name": s.light_model, "base_url": s.light_base_url,
                      "api_key": s.light_api_key or "", "model": s.light_model,
                      "thinking": s.light_thinking})
    return {
        "mt": mt, "main": main, "light": light,
        "mt_active": mt[0]["name"] if mt else "",
        "main_active": main[0]["name"] if main else "",
        "light_active": light[0]["name"] if light else "",
        "mt_engine": s.mt_engine,
    }


def _hot_reload(request: Request):
    from backend.app import _build_mt_engine
    from backend.config import load_settings
    from backend.orchestrator import Orchestrator
    settings = load_settings()
    request.app.state.settings = settings
    request.app.state.mt_engine = _build_mt_engine(settings)
    request.app.state.orchestrator = Orchestrator(settings)


@router.get("/profiles")
async def get_profiles(request: Request):
    data = _load(request)
    # 三组都要脱敏：api_key 只回布尔 has_key，绝不把明文 key 发回前端
    for group in ("mt", "main", "light"):
        for p in data.get(group, []):
            p["has_key"] = bool(p.get("api_key"))
            p["api_key"] = ""
    data.setdefault("live_model", "")
    return {"ok": True, **data}


@router.post("/profiles")
async def save_profiles(request: Request, body: ProfilesBody):
    # Blank api_key keeps the previously stored key for the same profile name.
    old = _load(request)
    old_mt = {p["name"]: p for p in old.get("mt", [])}
    old_main = {p["name"]: p for p in old.get("main", [])}
    mt_list = []
    for p in body.mt:
        d = p.dict()
        if not d["api_key"] and d["name"] in old_mt:
            d["api_key"] = old_mt[d["name"]].get("api_key", "")
        mt_list.append(d)
    main_list = []
    for p in body.main:
        d = p.dict()
        if not d["api_key"] and d["name"] in old_main:
            d["api_key"] = old_main[d["name"]].get("api_key", "")
        main_list.append(d)
    old_light = {p["name"]: p for p in old.get("light", [])}
    light_list = []
    for p in body.light:
        d = p.dict()
        if not d["api_key"] and d["name"] in old_light:
            d["api_key"] = old_light[d["name"]].get("api_key", "")
        light_list.append(d)
    data = {
        "mt": mt_list,
        "main": main_list,
        "light": light_list,
        "mt_active": body.mt_active,
        "main_active": body.main_active,
        "light_active": body.light_active,
        "mt_engine": body.mt_engine,
        "live_model": body.live_model,
    }
    p = _profiles_path(request)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    _set_env("MT_ENGINE", body.mt_engine)
    mt_active = next((x for x in data["mt"] if x["name"] == body.mt_active), None)
    if mt_active:
        _set_env("MT_BASE_URL", mt_active["base_url"])
        _set_env("MT_API_KEY", mt_active["api_key"])
        _set_env("MT_MODEL", mt_active["model"])
    main_active = next((x for x in data["main"] if x["name"] == body.main_active), None)
    if main_active:
        _set_env("MAIN_BASE_URL", main_active["base_url"])
        _set_env("MAIN_API_KEY", main_active["api_key"])
        _set_env("MAIN_MODEL", main_active["model"])
    light_active = next((x for x in data["light"] if x["name"] == body.light_active), None)
    if light_active:
        _set_env("LIGHT_BASE_URL", light_active["base_url"])
        _set_env("LIGHT_API_KEY", light_active["api_key"])
        _set_env("LIGHT_MODEL", light_active["model"])
    if body.live_model.strip():
        _set_env("LIVETRANSLATE_MODEL", body.live_model.strip())
    for env_key, profile in (("MAIN_THINKING", main_active),
                             ("LIGHT_THINKING", light_active),
                             ("MT_THINKING", mt_active)):
        if profile:
            _set_env(env_key, profile.get("thinking", "") or "")

    _hot_reload(request)
    return {"ok": True, "message": "已保存并切换"}

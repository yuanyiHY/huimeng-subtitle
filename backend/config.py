"""Configuration loader for 绘梦subtitle.

Reads config.yaml at project root, then overlays environment variables so a
pure-local machine can run with an empty .env (everything defaults to None/off).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- Storage path policy ---
# New brand-consistent defaults, plus the legacy "korean-studio" paths that
# existing installs may still be using.
_NEW_MODELS = "~/Library/Application Support/intrealtimetranslate/models"
_NEW_ARCHIVES = "~/Library/Application Support/intrealtimetranslate/archives"
_NEW_RECORDINGS = "~/Documents/intrealtimetranslate-recordings"
_OLD_APP_SUPPORT = "~/Library/Application Support/korean-studio"
_OLD_RECORDINGS = "~/Documents/korean-studio-recordings"
_OLD_MODELS = "~/Library/Application Support/korean-studio/models"
_OLD_ARCHIVES = "~/Library/Application Support/korean-studio/archives"

def env_file_path() -> Path:
    """配置文件位置。

    - 打包成 App 后由启动器设置 IRT_ENV_FILE，指向用户数据目录
      （App 包内是只读/带签名的，不能往里面写配置，否则签名会失效）
    - 开发时仍用项目目录下的 .env，保持原有习惯
    """
    override = os.environ.get("IRT_ENV_FILE")
    if override:
        return Path(override).expanduser()
    return PROJECT_ROOT / ".env"


try:
    from dotenv import load_dotenv
    load_dotenv(env_file_path())
except Exception:
    pass


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read an env var, returning None for empty strings."""
    val = os.environ.get(key, default)
    if val is None:
        return None
    val = val.strip()
    return val if val else None


class Settings:
    """Typed-ish accessor over the merged config dict."""

    def __init__(self, data: Dict[str, Any]):
        self._d = data or {}

    def get(self, *path: str, default: Any = None) -> Any:
        node: Any = self._d
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    # --- server ---
    @property
    def host(self) -> str:
        return str(self.get("server", "host", default="127.0.0.1"))

    @property
    def port(self) -> int:
        return int(self.get("server", "port", default=8000))

    # --- asr ---
    @property
    def asr_engine(self) -> str:
        return str(self.get("asr", "engine", default="local"))

    @property
    def asr_model(self) -> str:
        return str(self.get("asr", "local", "model",
                            default="mlx-community/whisper-large-v3-turbo"))

    @property
    def asr_language(self) -> str:
        return str(self.get("asr", "local", "language", default="ko"))

    # --- mt ---
    @property
    def mt_engine(self) -> str:
        return str(_env("MT_ENGINE", self.get("mt", "engine", default="auto")))

    @property
    def mt_cloud_base_url(self) -> Optional[str]:
        return _env("MT_BASE_URL", self.get("mt", "cloud", "base_url"))

    @property
    def mt_cloud_api_key(self) -> Optional[str]:
        return _env("MT_API_KEY", self.get("mt", "cloud", "api_key"))

    @property
    def mt_cloud_model(self) -> Optional[str]:
        val = _env("MT_MODEL", self.get("mt", "cloud", "model"))
        return str(val) if val else None

    @property
    def livetranslate_model(self) -> str:
        """实时同传（百炼 WebSocket 实时翻译）用的模型名。"""
        return str(_env("LIVETRANSLATE_MODEL") or "qwen3.5-livetranslate-flash-realtime")

    @property
    def mt_local_model(self) -> str:
        return str(self.get("mt", "local", "model",
                            default="nllb-200-distilled-600M"))

    @property
    def mt_local_int8(self) -> bool:
        return bool(self.get("mt", "local", "int8", default=True))

    @property
    def mt_local_qwen_model(self) -> str:
        return str(self.get("mt", "local_qwen", "model",
                            default="Qwen2.5-7B-Instruct-4bit-MLX"))

    # --- orchestrator ---
    @property
    def main_base_url(self) -> Optional[str]:
        return _env("MAIN_BASE_URL", self.get("orchestrator", "base_url"))

    @property
    def main_api_key(self) -> Optional[str]:
        return _env("MAIN_API_KEY", self.get("orchestrator", "api_key"))

    @property
    def main_model(self) -> Optional[str]:
        val = _env("MAIN_MODEL", self.get("orchestrator", "model"))
        return str(val) if val else None

    # --- 轻量实时模型（实时阶段的快速总结 / 重点提取）---
    @property
    def light_base_url(self) -> Optional[str]:
        return _env("LIGHT_BASE_URL") or self.main_base_url

    @property
    def light_api_key(self) -> Optional[str]:
        return _env("LIGHT_API_KEY") or self.main_api_key

    @property
    def light_model(self) -> Optional[str]:
        val = _env("LIGHT_MODEL") or self.main_model
        return str(val) if val else None

    # --- 思考强度（off / "" 标准 / deep），三个模型各配各的 ---
    @property
    def main_thinking(self) -> str:
        return str(_env("MAIN_THINKING") or "deep")

    @property
    def light_thinking(self) -> str:
        return str(_env("LIGHT_THINKING") or "off")

    @property
    def mt_thinking(self) -> str:
        return str(_env("MT_THINKING") or "off")

    @property
    def check_mt_on_start(self) -> bool:
        return bool(self.get("orchestrator", "check_mt_on_start", default=True))

    # --- paths ---
    @property
    def models_dir(self) -> Path:
        raw = str(self.get("models_dir", default=_NEW_MODELS))
        return _resolve_dir(raw, legacy=_OLD_MODELS if raw == _NEW_MODELS else None)

    @property
    def recordings_dir(self) -> Path:
        val = _env("RECORDINGS_DIR",
                   self.get("recordings_dir", default=_NEW_RECORDINGS))
        raw = str(val)
        return _resolve_dir(raw, legacy=_OLD_RECORDINGS if raw == _NEW_RECORDINGS else None)

    @property
    def archives_dir(self) -> Path:
        val = _env("ARCHIVES_DIR",
                   self.get("archives_dir", default=_NEW_ARCHIVES))
        raw = str(val)
        return _resolve_dir(raw, legacy=_OLD_ARCHIVES if raw == _NEW_ARCHIVES else None)

    @property
    def max_audio_seconds(self) -> int:
        return int(self.get("asr", "local", "max_seconds", default=12))


def _resolve_dir(raw: str, legacy: Optional[str] = None) -> Path:
    """Resolve one storage dir, falling back to its legacy location.

    The one-time directory move itself happens in ``_migrate_legacy_storage``;
    this helper only keeps the app working from the old path when that move
    was not possible (e.g. permissions), so user data never disappears.
    """
    path = Path(str(raw)).expanduser()
    if legacy and not path.exists():
        old = Path(legacy).expanduser()
        if old.exists():
            return old
    return path


def _migrate_legacy_storage() -> None:
    """Best-effort one-time move of legacy ``korean-studio`` data dirs.

    Idempotent: once the new dirs exist it becomes a no-op. Never deletes
    anything on failure — it just logs and leaves the old dirs in place.
    """
    pairs = [
        (Path(_OLD_APP_SUPPORT).expanduser(),
         Path("~/Library/Application Support/intrealtimetranslate").expanduser()),
        (Path(_OLD_RECORDINGS).expanduser(),
         Path(_NEW_RECORDINGS).expanduser()),
    ]
    for old, new in pairs:
        try:
            if old.exists() and not new.exists():
                new.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old), str(new))
                print(f"[config] 存储目录已迁移: {old} -> {new}", flush=True)
        except Exception as exc:  # noqa: BLE001 - never block startup on this
            print(f"[config] 存储目录迁移失败（继续用旧路径）: {old}: {exc}", flush=True)


def load_settings(extra: Optional[Dict[str, Any]] = None) -> Settings:
    # Re-read .env on every load so hot-saved storage/cloud settings take effect.
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file_path(), override=True)
    except Exception:
        pass
    _migrate_legacy_storage()
    data = _load_yaml(PROJECT_ROOT / "config.yaml")
    if extra:
        data = _deep_merge(data, extra)
    return Settings(data)


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result

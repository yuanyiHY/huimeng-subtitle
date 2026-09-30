"""Orchestrator: the "main model" that checks translation availability and does
course summarization (summary / outline / review questions).

For the skeleton this talks to any OpenAI-compatible /v1/chat/completions
endpoint over plain urllib (no extra deps). If it cannot reach the endpoint or
no key/base_url is configured, it falls back to a graceful degraded result so
the UI can always show a meaningful state.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from backend.config import Settings

DEFAULT_SUMMARY_PROMPT = (
    "你是一名专业课程助教。请根据以下课程转写稿，整理出：\n"
    "1) 一段课程摘要；\n"
    "2) 章节提纲（分点）；\n"
    "3) 3~5 道复习题。\n"
    "用中文输出，结构清晰。\n\n转写稿：\n{transcript}"
)


# 思考强度 → 输出预算 / 超时倍数（推理模型的思考会占用输出预算，必须同步放大）
_THINK_SCALE = {"off": (0.8, 1.0), "": (1.0, 1.0), "deep": (3.0, 3.0)}


def thinking_payload(base_url: Optional[str], thinking: str) -> dict:
    """把「思考强度」翻译成各家端点认识的开参数。

    - 阿里云百炼：enable_thinking (+ thinking_budget)
    - 深度求索官方：thinking.type = enabled / disabled
    - 其它 OpenAI 兼容端点：只在需要强思考时给 reasoning_effort，避免不认参数
    """
    if thinking not in ("off", "deep"):
        return {}
    host = (base_url or "").lower()
    enabled = thinking == "deep"
    if "dashscope" in host or "aliyuncs" in host:
        payload = {"enable_thinking": enabled}
        if enabled:
            payload["thinking_budget"] = 3000
        return payload
    if "deepseek" in host:
        return {"thinking": {"type": "enabled" if enabled else "disabled"}}
    return {"reasoning_effort": "high"} if enabled else {}


def _chat_completion_ex(
    base_url: Optional[str],
    api_key: Optional[str],
    model: Optional[str],
    system: str,
    user: str,
    max_tokens: int = 300,
    timeout: int = 15,
    thinking: str = "",
) -> "tuple[Optional[str], Optional[ErrorCode]]":
    """Call an OpenAI-compatible chat endpoint.

    Returns ``(text, None)`` on success or ``(None, ErrorCode)`` on failure.
    兼容推理模型（reasoning_content）：当正文为空但返回了思考内容时
    （deepseek-flash / *-reasoner 等），自动加大输出预算重试一次。
    """
    from backend.errors import ErrorCode, classify_url_error
    if not base_url or not model:
        return None, ErrorCode.MAIN_MODEL_MISSING
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    factor, timeout_factor = _THINK_SCALE.get(thinking, (1.0, 1.0))
    budget = int(max_tokens * factor)
    tmo = int(timeout * timeout_factor)
    extra = thinking_payload(base_url, thinking)

    def _post(tokens: int, t, with_extra: bool = True) -> dict:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": tokens,
            "temperature": 0.2,
        }
        if with_extra and extra:
            payload.update(extra)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=t) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _pick(body: dict):
        choice = (body.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = (msg.get("content") or "").strip()
        reasoning = (msg.get("reasoning_content") or "").strip()
        finish = choice.get("finish_reason") or ""
        return content, reasoning, finish

    try:
        body = _post(budget, tmo)
    except urllib.error.HTTPError as exc:
        # 端点不认思考参数（400/422）→ 去掉参数重试一次，保证功能不因此挂掉
        if extra and exc.code in (400, 422):
            try:
                body = _post(budget, tmo, with_extra=False)
            except Exception as exc2:  # noqa: BLE001
                return None, classify_url_error(exc2)
        else:
            return None, classify_url_error(exc)
    except Exception as exc:  # noqa: BLE001 - 统一归类为错误码
        return None, classify_url_error(exc)

    content, reasoning, finish = _pick(body)
    if not content and finish == "length":
        # 思考吃掉了输出预算 → 加大预算重试一次（含更宽的超时）
        bigger = min(max(budget * 2, 2000), 8000)
        if bigger > budget:
            try:
                body = _post(bigger, int(tmo * 1.4))
                content, reasoning, finish = _pick(body)
            except Exception as exc:  # noqa: BLE001
                return None, classify_url_error(exc)
    if not content:
        if finish == "stop":
            # 模型正常结束但选择不输出（例如“这段没有值得记录的内容”）
            # → 属于合法的空结果，不是错误
            return "", None
        return None, ErrorCode.EMPTY_RESPONSE
    return content, None


def _chat_completion(
    base_url: Optional[str],
    api_key: Optional[str],
    model: Optional[str],
    system: str,
    user: str,
    max_tokens: int = 300,
    timeout: int = 15,
) -> Optional[str]:
    """兼容旧调用：成功返回文本，失败返回 None。"""
    text, _ = _chat_completion_ex(base_url, api_key, model, system, user,
                                  max_tokens=max_tokens, timeout=timeout)
    return text


class Orchestrator:
    def __init__(self, settings: Settings):
        self.settings = settings

    def check_translation(self) -> Dict[str, Any]:
        """Minimal probe to the MT endpoint."""
        s = self.settings
        if not s.mt_cloud_base_url or not s.mt_cloud_model:
            return {"ok": False, "engine": "local-nllb",
                    "message": "未配置云端翻译模型，已降级本地 NLLB"}
        from backend.mt.openai_engine import OpenAIMTEngine
        eng = OpenAIMTEngine(s.mt_cloud_base_url, s.mt_cloud_api_key,
                             s.mt_cloud_model, timeout=8)
        try:
            out = eng.translate(["hi"])
            ok = bool(out and out[0])
        except Exception:
            ok = False
        if ok:
            return {"ok": True, "engine": "cloud", "message": "🟢 云端翻译可用"}
        return {"ok": False, "engine": "local-nllb",
                "message": "🟡 云端不可用，已降级本地 NLLB"}

    def check_main(self) -> Dict[str, Any]:
        """Probe the main model endpoint."""
        s = self.settings
        if not s.main_base_url or not s.main_model:
            return {"ok": False, "message": "未配置主模型 Base URL / Model"}
        text, code = _chat_completion_ex(
            s.main_base_url, s.main_api_key, s.main_model,
            "You are a health check.", "hi", max_tokens=64, timeout=10,
        )
        from backend.errors import ErrorCode
        # EMPTY_RESPONSE 说明 HTTP 已通（推理模型小预算下只思考不输出正文）
        ok = text is not None or code == ErrorCode.EMPTY_RESPONSE
        return {"ok": ok, "engine": "main",
                "message": "🟢 主模型可用" if ok else "🟡 主模型不可用（检查 Key/网络）"}

    def check_light(self) -> Dict[str, Any]:
        """Probe the lightweight realtime model (falls back to the main model)."""
        s = self.settings
        if not s.light_base_url or not s.light_model:
            return {"ok": False, "message": "未配置轻量实时模型 Base URL / Model"}
        text, code = _chat_completion_ex(
            s.light_base_url, s.light_api_key, s.light_model,
            "You are a health check.", "hi", max_tokens=64, timeout=10,
        )
        from backend.errors import ErrorCode
        ok = text is not None or code == ErrorCode.EMPTY_RESPONSE
        return {"ok": ok, "engine": "light",
                "message": "🟢 轻量实时模型可用" if ok else "🟡 轻量实时模型不可用（检查 Key/网络）"}

    def summarize(self, transcript: str, extra_instruction: str = "") -> Dict[str, Any]:
        """Bucket the transcript through the main model."""
        s = self.settings
        base_url, api_key, model = s.main_base_url, s.main_api_key, s.main_model
        prompt = DEFAULT_SUMMARY_PROMPT.format(transcript=transcript[:6000])
        if extra_instruction.strip():
            prompt += "\n\n额外要求：" + extra_instruction.strip()
        text, err_code = _chat_completion_ex(
            base_url, api_key, model, "你是一名专业课程助教。", prompt,
            max_tokens=1600, timeout=30, thinking=self.settings.main_thinking,
        )
        if text:
            return {"ok": True, "engine": "main", "text": text}
        # Degraded fallback: produce something useful without an LLM.
        from backend.errors import ErrorCode
        return {
            "ok": True,
            "engine": "local-template",
            "code": (err_code or ErrorCode.MAIN_MODEL_MISSING).value,
            "text": (
                "主模型未配置或暂时不可用。以下是基于转写稿的骨架整理：\n\n"
                "【课程摘要】\n（接入主模型后可生成高质量摘要）\n\n"
                "【章节提纲】\n- 待接入主模型生成\n\n"
                "【复习题】\n- 待接入主模型生成\n\n"
                "提示：在设置页配置主模型 Base URL / API Key / Model 后即可使用真实整理。"
            ),
        }


orchestrator: Optional[Orchestrator] = None


def get_orchestrator(settings: Settings) -> Orchestrator:
    global orchestrator
    if orchestrator is None:
        orchestrator = Orchestrator(settings)
    return orchestrator

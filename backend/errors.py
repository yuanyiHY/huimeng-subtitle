"""统一错误码与 API 错误响应（后端吐 code，前端翻人话）。

约定：API 失败响应统一结构 ——

    {"ok": false, "code": "API_KEY_INVALID", "message": "...", "hint": "..."}

前端 ``error-handler.js`` 依据 ``code`` 映射友好文案与解决方案；
``message``/``hint`` 作为兜底和上下文补充。

参考 Coursedude 的做法：错误码在后端产生，前端只负责展示。
"""
from __future__ import annotations

import json
import socket
import urllib.error
from enum import Enum
from typing import Any, Dict, Optional


class ErrorCode(str, Enum):
    # --- 配置类 ---
    API_KEY_MISSING = "API_KEY_MISSING"          # 没配 Key
    API_KEY_INVALID = "API_KEY_INVALID"          # Key 无效/过期/欠费
    MAIN_MODEL_MISSING = "MAIN_MODEL_MISSING"    # 主模型未配置
    MT_NOT_CONFIGURED = "MT_NOT_CONFIGURED"      # 翻译引擎未配置

    # --- 引擎/模型类 ---
    ASR_UNAVAILABLE = "ASR_UNAVAILABLE"          # 本地 ASR 未就绪
    MT_UNAVAILABLE = "MT_UNAVAILABLE"            # 翻译引擎不可用
    MODEL_NOT_INSTALLED = "MODEL_NOT_INSTALLED"  # 模型未下载
    MODEL_LOAD_FAILED = "MODEL_LOAD_FAILED"      # 模型加载失败
    ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"    # 引擎通用不可用

    # --- 网络类 ---
    NETWORK_ERROR = "NETWORK_ERROR"              # 连不上（DNS/拒绝/断网）
    TIMEOUT = "TIMEOUT"                          # 请求超时
    RATE_LIMITED = "RATE_LIMITED"                # 429 限流
    SERVER_ERROR = "SERVER_ERROR"                # 对端 5xx

    # --- 文件/磁盘 ---
    FILE_INVALID = "FILE_INVALID"                # 文件不合法/损坏
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    DISK_FULL = "DISK_FULL"                      # 磁盘空间不足

    # --- 一般 ---
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    INTERNAL = "INTERNAL"                        # 未分类内部错误
    EMPTY_RESPONSE = "EMPTY_RESPONSE"            # 模型返回空正文（如推理预算被思考耗尽）


def api_error(code: ErrorCode | str, message: str, hint: Optional[str] = None,
              status_ok: bool = False, **extra: Any) -> Dict[str, Any]:
    """构造统一错误响应体。"""
    resp: Dict[str, Any] = {
        "ok": status_ok,
        "code": code.value if isinstance(code, ErrorCode) else str(code),
        "message": message,
    }
    if hint:
        resp["hint"] = hint
    resp.update(extra)
    return resp


def classify_url_error(exc: BaseException) -> ErrorCode:
    """把 urllib / socket 异常归类成错误码。"""
    if isinstance(exc, urllib.error.HTTPError):
        status = getattr(exc, "code", 0)
        if status in (401, 403):
            return ErrorCode.API_KEY_INVALID
        if status == 429:
            return ErrorCode.RATE_LIMITED
        if status >= 500:
            return ErrorCode.SERVER_ERROR
        return ErrorCode.INTERNAL
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return ErrorCode.TIMEOUT
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, socket.timeout):
            return ErrorCode.TIMEOUT
        return ErrorCode.NETWORK_ERROR
    if isinstance(exc, (json.JSONDecodeError, KeyError, ValueError)):
        return ErrorCode.INTERNAL
    return ErrorCode.INTERNAL


def classify_exception(exc: BaseException) -> ErrorCode:
    """通用异常 → 错误码（含磁盘空间不足的识别）。"""
    text = str(exc).lower()
    if "no space left" in text or "disk full" in text:
        return ErrorCode.DISK_FULL
    if "connection refused" in text or "name or service not known" in text \
            or "nodename nor servname" in text or "network is unreachable" in text:
        return ErrorCode.NETWORK_ERROR
    return classify_url_error(exc)


_MESSAGES: Dict[str, str] = {
    ErrorCode.API_KEY_MISSING: "尚未配置 API 密钥",
    ErrorCode.API_KEY_INVALID: "API 密钥无效或已过期",
    ErrorCode.MAIN_MODEL_MISSING: "主模型未配置",
    ErrorCode.MT_NOT_CONFIGURED: "翻译引擎未配置",
    ErrorCode.ASR_UNAVAILABLE: "本地语音识别未就绪",
    ErrorCode.MT_UNAVAILABLE: "翻译引擎不可用",
    ErrorCode.MODEL_NOT_INSTALLED: "模型尚未下载",
    ErrorCode.MODEL_LOAD_FAILED: "模型加载失败",
    ErrorCode.ENGINE_UNAVAILABLE: "引擎不可用",
    ErrorCode.NETWORK_ERROR: "网络连接失败",
    ErrorCode.TIMEOUT: "请求超时",
    ErrorCode.RATE_LIMITED: "请求过于频繁（被限流）",
    ErrorCode.SERVER_ERROR: "服务端暂时不可用",
    ErrorCode.FILE_INVALID: "文件不合法或已损坏",
    ErrorCode.FILE_NOT_FOUND: "文件不存在",
    ErrorCode.DISK_FULL: "磁盘空间不足",
    ErrorCode.INVALID_ARGUMENT: "参数不合法",
    ErrorCode.INTERNAL: "出现了一个内部错误",
    ErrorCode.EMPTY_RESPONSE: "模型返回了空内容",
}


def humanize(code: ErrorCode | str) -> str:
    """错误码 → 一行中文短提示（供后端在 message 中复用）。"""
    key = code.value if isinstance(code, ErrorCode) else str(code)
    return _MESSAGES.get(key, "出现了一个问题")

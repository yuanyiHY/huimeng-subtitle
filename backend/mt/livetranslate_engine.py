"""百炼实时语音翻译引擎（Qwen3.5-LiveTranslate-Realtime）。

通过 WebSocket 直连百炼实时接口：音频边发边翻，流式返回原文识别与译文。
用于「实时同传模式」——延迟显著低于 本地 whisper + 文本翻译 的两段式管线。

协议要点（官方文档）：
- 端点 wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model=<model>
- 鉴权 Authorization: Bearer <DASHSCOPE_API_KEY>
- 上行 input_audio_buffer.append（base64，16kHz/16bit/mono PCM）
- 下行 conversation.item.input_audio_transcription.*（原文）、response.text.*（译文）
- 结束前须发 session.finish
"""
from __future__ import annotations

import base64
import json
import threading
from typing import Callable, Optional

# 百炼实时语音翻译接口（WebSocket）。模型名可在「设置 → 模型设置 → 实时同传模型」里改
DEFAULT_MODEL = "qwen3.5-livetranslate-flash-realtime"
WS_BASE = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"


def ws_url(model: str) -> str:
    return f"{WS_BASE}?model={model}"

# 项目语言代码 → 百炼实时翻译语言代码
LT_LANG = {
    "ko": "ko",
    "zh": "zh",
    "zh-TW": "zh-tw",
    "en": "en",
    "ja": "ja",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "ru": "ru",
}


class LiveTranslateSession:
    """一次实时同传会话：音频上行 + 事件下行（跑在独立线程）。"""

    def __init__(self, api_key: str, src: str = "ko", tgt: str = "zh",
                 on_event: Optional[Callable[[dict], None]] = None,
                 model: Optional[str] = None):
        self.model = (model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        self.api_key = api_key
        self.src = LT_LANG.get(src, src)
        self.tgt = LT_LANG.get(tgt, tgt)
        self.on_event = on_event
        self.ws = None
        self.running = False
        self.started = False
        self.error: Optional[str] = None
        self._recv_thread: Optional[threading.Thread] = None
        self._send_lock = threading.Lock()
        self._ready = threading.Event()

    def start(self, timeout: float = 20.0) -> bool:
        self.running = True
        self._recv_thread = threading.Thread(target=self._run, daemon=True)
        self._recv_thread.start()
        ok = self._ready.wait(timeout)
        return bool(ok and self.started)

    def _run(self) -> None:
        from websockets.sync.client import connect
        try:
            with connect(ws_url(self.model),
                         additional_headers={"Authorization": f"Bearer {self.api_key}"},
                         open_timeout=20) as ws:
                self.ws = ws
                # session.created 里带着服务端对该模型的默认会话配置。
                # 不同版本字段会变（3.5 是 "pcm" + 无默认转写模型；
                # 3.8 是 "pcm16" + 默认 gummy-realtime-v1），所以这里
                # 以服务端下发的默认值为准，只覆盖必要的部分。
                created = json.loads(ws.recv())
                defaults = created.get("session", {}) if isinstance(created, dict) else {}
                session_cfg = {
                    "modalities": ["text"],
                    # 必须显式指定音色：3.8 的默认音色 Chelsie 服务端不支持，
                    # 不指定就会被 1011 掐断连接（Tina 在 3.5 / 3.8 上都可用）
                    "voice": "Tina",
                    "translation": {"language": self.tgt},
                }
                audio_fmt = defaults.get("input_audio_format")
                if audio_fmt:
                    session_cfg["input_audio_format"] = audio_fmt
                if not defaults.get("input_audio_transcription"):
                    # 老版本没有默认转写模型，需要显式指定
                    session_cfg["input_audio_transcription"] = {
                        "model": "qwen3-asr-flash-realtime",
                        "language": self.src,
                    }
                self.audio_format = session_cfg.get("input_audio_format", "pcm")
                print(f"[livetranslate] 协商格式={self.audio_format} "
                      f"默认转写={defaults.get('input_audio_transcription', {})}", flush=True)
                ws.send(json.dumps({"type": "session.update", "session": session_cfg}))
                while self.running:
                    try:
                        ev = json.loads(ws.recv(timeout=0.5))
                    except TimeoutError:
                        continue
                    etype = ev.get("type", "")
                    if etype == "session.updated":
                        self.started = True
                        self._ready.set()
                    elif etype == "error":
                        self.error = str(ev)[:300]
                        self._ready.set()
                    if self.on_event:
                        try:
                            self.on_event(ev)
                        except Exception:
                            pass
                    if etype == "session.finished":
                        break
        except Exception as exc:  # pragma: no cover
            self.error = f"{type(exc).__name__}: {str(exc)[:200]}"
            self._ready.set()
        finally:
            self.running = False

    def send_audio(self, pcm_bytes: bytes) -> None:
        if not (self.started and self.running and self.ws):
            return
        try:
            with self._send_lock:
                self.ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(pcm_bytes).decode("ascii"),
                }))
        except Exception as exc:
            # 以前这里静默 pass，导致"连上了但一个字都没有"完全查不出原因
            if not self.error:
                self.error = f"实时同传发送失败：{type(exc).__name__}: {str(exc)[:160]}"
            self.running = False

    def stop(self, wait: float = 5.0) -> None:
        if not self.running:
            return
        self.running = False

        # 在新线程里发 session.finish，避免发送阻塞调用方
        def _finish():
            try:
                with self._send_lock:
                    if self.ws:
                        self.ws.send(json.dumps({"type": "session.finish"}))
            except Exception:
                pass

        t = threading.Thread(target=_finish, daemon=True)
        t.start()
        t.join(timeout=2.0)
        if self._recv_thread:
            self._recv_thread.join(timeout=wait)


class SubtitleAccumulator:
    """把百炼事件累积成字幕条目（供轮询渲染），供采音/流式两条路径共用。

    配对策略（依据事件字段）：
    - 原文：用 input_audio_buffer.speech_started 的 item_id 建条目，
      后续 conversation.item.input_audio_transcription.* 带同 item_id 写入。
    - 译文：response.text.* 属于当前轮次，写入当前条目。
    - 时间轴：优先用事件自带的 audio_start_ms / audio_end_ms（毫秒）。
    """

    def __init__(self, live_list: list, elapsed_fn=None):
        self.live = live_list
        self.elapsed_fn = elapsed_fn or (lambda: 0.0)
        self._by_item: dict = {}
        self._current: dict | None = None

    def _now(self) -> float:
        try:
            return round(float(self.elapsed_fn()), 1)
        except Exception:
            return 0.0

    def on_event(self, ev: dict) -> None:
        et = ev.get("type", "")
        item_id = ev.get("item_id")

        if et == "input_audio_buffer.speech_started":
            # 先固化上一句
            if self._current and self._current.get("partial"):
                self._current["partial"] = False
                self._current["end"] = self._now()
            ms = ev.get("audio_start_ms")
            start_s = (ms / 1000.0) if isinstance(ms, (int, float)) else self._now()
            s = {"ko": "", "zh": "", "start": round(start_s, 1),
                 "end": round(start_s, 1), "partial": True}
            self.live.append(s)
            self._current = s
            if item_id:
                self._by_item[item_id] = s

        elif et == "input_audio_buffer.speech_stopped":
            s = self._by_item.get(item_id) or self._current
            ms = ev.get("audio_end_ms")
            if s is not None and isinstance(ms, (int, float)):
                s["end"] = round(ms / 1000.0, 1)

        elif et == "conversation.item.input_audio_transcription.text":
            s = self._by_item.get(item_id) or self._current
            if s is not None:
                s["ko"] = (ev.get("text", "") + ev.get("stash", "")).strip()

        elif et == "conversation.item.input_audio_transcription.completed":
            s = self._by_item.get(item_id) or self._current
            if s is not None:
                s["ko"] = (ev.get("transcript", "") or s.get("ko", "")).strip()
            self._by_item.pop(item_id, None)

        elif et == "response.text.text":
            s = self._current
            if s is not None:
                s["zh"] = (ev.get("text", "") + ev.get("stash", "")).strip()

        elif et == "response.text.done":
            s = self._current
            if s is not None:
                s["zh"] = (ev.get("text", "") or s.get("zh", "")).strip()
                s["end"] = self._now()
                s["partial"] = False

        elif et == "response.done":
            s = self._current
            if s is not None:
                s["end"] = self._now()
                s["partial"] = False
            self._current = None

    def finish(self) -> None:
        """收尾：把进行中的条目固化。"""
        for s in self.live:
            if s.get("partial"):
                s["partial"] = False
                s["end"] = self._now()
        self._by_item.clear()
        self._current = None

"""原生麦克风采集模块（含两种引擎模式）。

- mode="local"    : 本地 whisper 转写 + 云端/本地翻译（两段式，可离线）
- mode="realtime" : 百炼实时同传（音频直发云端，边说边翻，低延迟）

pywebview 的 WKWebView 不提供 navigator.mediaDevices，打包 App 的实时字幕
由后端用 sounddevice 直接采集麦克风；前端通过 HTTP 接口控制开始/停止，
字幕走 /api/live/subtitles 轮询渲染（支持 partial 流式更新）。
"""
from __future__ import annotations

import queue
import threading
from datetime import datetime

import numpy as np
from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.api.stream import LIVE_SUBTITLES, _write_recording

router = APIRouter()

SR = 16000
MIN_SAMPLES = int(1.5 * SR)
MAX_SAMPLES = int(12 * SR)
TAIL_SAMPLES = int(0.6 * SR)


class CaptureStart(BaseModel):
    src: str = "ko"
    tgt: str = "zh"
    mode: str = "local"  # local | realtime
    device: str = "default"  # 前端选择的输入设备名，default = 系统默认


class MonitorStart(BaseModel):
    device: str = "default"


def _resolve_device(name: str | None):
    """把前端选择的设备名解析成 sounddevice 的设备序号。

    浏览器给的是设备标签（如「麦克风 (ROSE FIRST ANGEL)」），sounddevice 给的是
    设备名（如「ROSE FIRST ANGEL」），两边做双向包含匹配；匹配不到就用系统默认。
    """
    if not name or name in ("default", "系统默认麦克风"):
        return None
    try:
        import sounddevice as sd
        lowered = str(name).lower()
        devices = list(sd.query_devices())
        inputs = [(i, str(d.get("name", ""))) for i, d in enumerate(devices)
                  if d.get("max_input_channels", 0) > 0]
        for idx, dev_name in inputs:                       # 设备名是标签的一部分
            if dev_name and dev_name.lower() in lowered:
                return idx
        for idx, dev_name in inputs:                       # 标签是设备名的一部分
            if dev_name and lowered in dev_name.lower():
                return idx
    except Exception:
        return None
    return None


class MicMonitor:
    """只测输入电平，不录音、不转写：给设置页的采集音量条用。"""

    def __init__(self):
        self.active = False
        self.rms = 0.0
        self.peak = 0.0
        self.device = "default"
        self.error: str | None = None
        self._stream = None
        self._lock = threading.Lock()

    def start(self, device=None, label: str = "default") -> bool:
        if self.active:
            return True
        import sounddevice as sd
        self.error = None
        self.device = label
        try:
            self._stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                          device=device, callback=self._cb)
            self._stream.start()
        except Exception as exc:  # noqa: BLE001 - 设备被占用/无权限都要给出人话提示
            self.error = str(exc)[:200]
            self._stream = None
            self.active = False
            return False
        self.active = True
        return True

    def _cb(self, indata, frames, time_info, status):
        if indata is None or not len(indata):
            return
        arr = indata[:, 0]
        rms = float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))
        with self._lock:
            self.rms = round(rms, 4)
            self.peak = round(float(np.max(np.abs(arr))), 4)

    def stop(self) -> None:
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None
        self.active = False
        with self._lock:
            self.rms = 0.0
            self.peak = 0.0

    def status(self) -> dict:
        with self._lock:
            return {"active": self.active, "rms": self.rms, "peak": self.peak,
                    "device": self.device, "error": self.error}


class NativeCapture:
    def __init__(self):
        self.active = False
        self.paused = False
        self.mode = "local"
        self.error: str | None = None
        self._q = queue.Queue()
        self._stream = None
        self._thread = None
        self._lock = threading.Lock()
        self._proc_lock = threading.Lock()
        self.lt = None  # LiveTranslateSession（realtime 模式）
        self.acc = None  # SubtitleAccumulator（realtime 模式）
        self.asr = None
        self.mt = None
        self.rec_dir = None
        self.src = "ko"
        self.tgt = "zh"
        self.started_at = ""
        self.rms_now = 0.0
        self.all_chunks: list = []
        self.buffer: list = []
        self.total_samples = 0
        self.elapsed = 0

    # ---------- 生命周期 ----------
    def start(self, asr, mt, rec_dir, src="ko", tgt="zh",
              mode="local", api_key=None, device=None, model=None) -> bool:
        if self.active:
            return False
        import sounddevice as sd
        self.error = None
        self.paused = False
        self.mode = mode if mode in ("local", "realtime") else "local"
        self.asr, self.mt, self.rec_dir = asr, mt, rec_dir
        self.src, self.tgt = src, tgt
        self.started_at = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.all_chunks, self.buffer = [], []
        self.total_samples = self.elapsed = 0
        self.rms_now = 0.0
        LIVE_SUBTITLES.clear()

        if self.mode == "realtime":
            if not api_key:
                self.error = "未配置云端 API Key（实时同传需要联网）"
                return False
            from backend.mt.livetranslate_engine import (LiveTranslateSession,
                                                         SubtitleAccumulator)
            self.acc = SubtitleAccumulator(LIVE_SUBTITLES,
                                           lambda: self.elapsed / SR)
            self.lt = LiveTranslateSession(api_key, src, tgt,
                                           on_event=self.acc.on_event, model=model)
            if not self.lt.start():
                self.error = self.lt.error or "实时同传连接失败"
                self.lt = None
                return False

        self.active = True
        try:
            self._stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                          device=device, callback=self._cb)
            self._stream.start()
        except Exception as exc:  # noqa: BLE001 - 设备打不开时要说清楚原因
            self.active = False
            self.error = f"麦克风打不开：{str(exc)[:160]}"
            if self.lt:
                self.lt.stop()
                self.lt = None
            self.acc = None
            return False
        if self.mode == "local":
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()
        print(f"[capture] 开始采音 mode={self.mode} {src}->{tgt} @ {self.started_at}",
              flush=True)
        return True

    def _cb(self, indata, frames, time_info, status):
        if not (self.active and not self.paused and indata is not None):
            return
        arr = indata[:, 0].copy()
        self.rms_now = float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))
        if self.mode == "realtime":
            with self._lock:
                self.all_chunks.append(arr)
                self.elapsed += len(arr)
            pcm16 = (np.clip(arr, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
            if self.lt:
                self.lt.send_audio(pcm16)
        else:
            self._q.put(arr)

    # ---------- realtime 事件处理 ----------
    # （字幕累积逻辑在 SubtitleAccumulator，供采音/流式两条路径共用）

    # ---------- local 模式处理 ----------
    def _worker(self):
        while self.active or not self._q.empty():
            try:
                arr = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            with self._lock:
                self.all_chunks.append(arr)
                self.buffer.append(arr)
                self.total_samples += len(arr)
                self.elapsed += len(arr)
                if self.total_samples >= MAX_SAMPLES:
                    self._cut(force=True)
                elif self.total_samples >= MIN_SAMPLES + TAIL_SAMPLES:
                    tail = np.concatenate(self.buffer)[-TAIL_SAMPLES:]
                    tail_rms = float(np.sqrt(np.mean(tail.astype(np.float64) ** 2)))
                    if tail_rms < 0.015:
                        self._cut()
        with self._lock:
            if self.buffer:
                self._cut(force=True)

    def _cut(self, force: bool = False):
        if self.total_samples < MIN_SAMPLES and not force:
            return
        audio = np.concatenate(self.buffer).astype(np.float32)
        start_sec = (self.elapsed - self.total_samples) / SR
        self.buffer, self.total_samples = [], 0
        threading.Thread(target=self._process, args=(audio, start_sec),
                         daemon=True).start()

    def _process(self, audio, start_sec):
        with self._proc_lock:
            try:
                rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
                if rms < 0.015:
                    return
                segs = self.asr.transcribe_array(audio, self.src)
                text = " ".join(s.text for s in segs).strip()
                if not text:
                    return
                zh = ""
                if self.mt and self.mt.available():
                    translations = self.mt.translate([text], self.src, self.tgt)
                    zh = (translations[0] if translations else "").strip()
                LIVE_SUBTITLES.append({
                    "ko": text, "zh": zh,
                    "start": round(start_sec, 1),
                    "end": round(start_sec + len(audio) / SR, 1),
                })
                print(f"[capture] {text!r} -> {zh!r}", flush=True)
            except Exception as exc:
                print(f"[capture] 处理失败: {exc}", flush=True)

    # ---------- 停止 ----------
    def stop(self):
        if not self.active:
            return
        self.active = False
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        if self.mode == "local" and self._thread:
            self._thread.join(timeout=3)
        if self.lt:
            self.lt.stop()
            self.lt = None
        if self.acc:
            self.acc.finish()
            self.acc = None
        # 收尾：把进行中的条目固化（local 模式无 acc，兜底处理）
        for s in LIVE_SUBTITLES:
            if s.get("partial"):
                s["partial"] = False
                s["end"] = round(self.elapsed / SR, 1)
        try:
            _write_recording(self.rec_dir, self.started_at,
                             self.all_chunks, list(LIVE_SUBTITLES))
        except Exception as exc:  # pragma: no cover
            print(f"[capture] 保存失败: {exc}", flush=True)
        self._stream = None
        self._thread = None
        print("[capture] 已停止", flush=True)

    def status(self):
        # 实时同传的错误发生在启动之后（比如服务端中途掐断），
        # 也一并报出来，避免界面一直显示"录制中"却没有任何文字
        err = self.error
        if not err and self.lt is not None:
            err = getattr(self.lt, "error", None)
        return {"active": self.active, "paused": self.paused, "rms": round(self.rms_now, 4),
                "src": self.src, "tgt": self.tgt, "mode": self.mode,
                "started_at": self.started_at, "error": err}


@router.post("/capture/start")
async def capture_start(request: Request, body: CaptureStart):
    import asyncio
    from functools import partial
    state = request.app.state
    loop = asyncio.get_running_loop()
    # 监听流与采集流会抢同一个设备，开录前先让出监听
    if state.monitor.active:
        await loop.run_in_executor(None, state.monitor.stop)
    # 放到线程池执行：连接云端可能耗时数秒，不能阻塞事件循环
    ok = await loop.run_in_executor(
        None, partial(
            state.capture.start,
            state.asr_engine, state.mt_engine, state.settings.recordings_dir,
            body.src, body.tgt, mode=body.mode,
            api_key=state.settings.mt_cloud_api_key,
            device=_resolve_device(body.device),
            model=state.settings.livetranslate_model,
        )
    )
    if not ok:
        return {"ok": False, "message": state.capture.error or "启动失败"}
    label = "实时同传模式" if state.capture.mode == "realtime" else "本地转写模式"
    return {"ok": True, "mode": state.capture.mode,
            "message": f"开始采音（{label}）"}


@router.post("/capture/monitor")
async def monitor_start(request: Request, body: MonitorStart):
    """设置页的采集音量条：开一路只测电平的输入流。"""
    import asyncio
    from functools import partial
    state = request.app.state
    if state.capture.active:
        return {"ok": True, "active": True, "source": "capture", **state.monitor.status()}
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(
        None, partial(state.monitor.start, _resolve_device(body.device), body.device)
    )
    if not ok:
        return {"ok": False, "active": False, "message": state.monitor.error or "无法打开麦克风"}
    return {"ok": True, "active": True, "source": "monitor", **state.monitor.status()}


@router.post("/capture/monitor/stop")
async def monitor_stop(request: Request):
    import asyncio
    state = request.app.state
    await asyncio.get_running_loop().run_in_executor(None, state.monitor.stop)
    return {"ok": True, "active": False}


@router.get("/capture/monitor")
async def monitor_status(request: Request):
    state = request.app.state
    if state.capture.active:  # 录制中直接复用采集流的电平
        return {"ok": True, "source": "capture", **state.monitor.status(),
                "active": True, "rms": round(state.capture.rms_now, 4)}
    return {"ok": True, "source": "monitor", **state.monitor.status()}


@router.post("/capture/stop")
async def capture_stop(request: Request):
    import asyncio
    loop = asyncio.get_running_loop()
    # 停止涉及线程 join 与写文件，同样不能阻塞事件循环
    await loop.run_in_executor(None, request.app.state.capture.stop)
    return {"ok": True, "message": "已停止"}


@router.post("/capture/pause")
async def capture_pause(request: Request):
    capture = request.app.state.capture
    if not capture.active:
        return {"ok": False, "message": "当前没有正在进行的会话"}
    capture.paused = True
    return {"ok": True, "message": "已暂停"}


@router.post("/capture/resume")
async def capture_resume(request: Request):
    capture = request.app.state.capture
    if not capture.active:
        return {"ok": False, "message": "当前没有正在进行的会话"}
    capture.paused = False
    return {"ok": True, "message": "已继续"}


@router.get("/capture/status")
async def capture_status(request: Request):
    return {"ok": True, **request.app.state.capture.status()}

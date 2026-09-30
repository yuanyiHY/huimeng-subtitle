"""绘梦subtitle entrypoint: start uvicorn backend, then open the pywebview window.

If pywebview is unavailable, fall back to opening the default browser so the
app always launches.
"""
from __future__ import annotations

import threading
import time

import uvicorn

from backend.app import create_app


def _serve(host: str, port: int):
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


def _open_window(host: str, port: int):
    url = f"http://{host}:{port}/"
    # 开发阶段默认用浏览器承载：localhost 是安全上下文，getUserMedia 会弹
    # 麦克风授权框，未打包的 python + pywebview 拿不到麦克风权限。
    import webbrowser
    webbrowser.open(url)


def open_pywebview(host: str, port: int):
    """Optional native window (needs packaged .app + mic permission)."""
    url = f"http://{host}:{port}/"
    import webview
    webview.create_window(
        "绘梦subtitle",
        url,
        width=1240,
        height=780,
        min_size=(980, 640),
        background_color="#FAFAF8",
    )
    webview.start()


def main():
    import sys
    use_window = "--window" in sys.argv  # .app 打包模式：原生窗口
    if use_window:
        # 告知后端这是原生窗口环境（前端据此走后端采音，不依赖 mediaDevices）
        import os
        os.environ["IRT_WINDOW_MODE"] = "1"
    app_config = create_app()
    settings = app_config.state.settings
    host, port = settings.host, settings.port

    server_thread = threading.Thread(
        target=_serve, args=(host, port), daemon=True
    )
    server_thread.start()

    # Give the server a moment to come up before loading the window.
    time.sleep(1.0)
    if use_window:
        open_pywebview(host, port)  # 阻塞到窗口关闭
        return  # 窗口已关：进程退出，释放端口，下次双击全新启动
    _open_window(host, port)

    # 浏览器模式保持进程存活（daemon 后端随之常驻）
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

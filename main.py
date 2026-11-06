#!/usr/bin/env python3
"""
Transcribe.OS - Native Desktop Application
Runs the offline server and loads the sleek SaaS UI in a native desktop window.
Zero command prompt windows, zero batch scripts.
"""

import os
import sys
import time
import socket
import threading
import webview

# Add project root to sys.path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from api.server import app


def is_port_in_use(port: int = 8000) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def start_server():
    if not is_port_in_use(8000):
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


def main():
    # Start the local FastAPI backend in a background daemon thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait briefly for server to bind
    for _ in range(30):
        if is_port_in_use(8000):
            break
        time.sleep(0.1)

    # Launch native desktop application window
    window = webview.create_window(
        title="Transcribe.OS — Universal Speech Engine",
        url="http://127.0.0.1:8000",
        width=1140,
        height=840,
        min_size=(920, 680),
        background_color="#000000",
        text_select=True
    )
    webview.start()


if __name__ == "__main__":
    main()


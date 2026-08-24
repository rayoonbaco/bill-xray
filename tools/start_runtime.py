"""Pass 31: robust Windows runtime launcher.

Owns port selection and server startup in Python so START_BILL_XRAY.bat does not
need fragile FOR /F command-substitution or nested quoting. It also confirms the
health endpoint belongs to the expected release before opening the browser.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# historical surface compatibility: Pass 31.5
EXPECTED_PASS = "31"
EXPECTED_SURFACE_PASS = "31.6"


def choose_free_port(start: int = 8000, count: int = 21) -> int:
    for port in range(start, start + count):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free localhost port found from {start} through {start + count - 1}")


def _health_matches(url: str, timeout: float = 0.8) -> bool:
    try:
        with urllib.request.urlopen(url + "api/health", timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return False
    return (str(payload.get("pass")) == EXPECTED_PASS and str(payload.get("surface_pass")) == EXPECTED_SURFACE_PASS and Path(payload.get("project_root", "")).resolve() == ROOT.resolve())


def main() -> int:
    port = choose_free_port()
    url = f"http://127.0.0.1:{port}/"
    print(f"Using local port: {port}", flush=True)
    if port != 8000:
        print("Port 8000 is occupied. Bill X-Ray will use a different port so an older runtime cannot hijack the browser.", flush=True)
    print(f"Starting Bill X-Ray surface Pass {EXPECTED_SURFACE_PASS} from: {ROOT}", flush=True)
    print(f"URL: {url}", flush=True)

    proc = subprocess.Popen([
        sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)
    ], cwd=str(ROOT))
    try:
        deadline = time.time() + 45
        while time.time() < deadline:
            if proc.poll() is not None:
                return int(proc.returncode or 1)
            if _health_matches(url):
                print("Health check confirms this browser target is Pass 31.6 from the expected project root.", flush=True)
                webbrowser.open(url)
                break
            time.sleep(0.4)
        else:
            print("ERROR: server started but the expected Pass 31.6 health fingerprint did not appear.", flush=True)
            proc.terminate()
            return 3
        return int(proc.wait())
    except KeyboardInterrupt:
        proc.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

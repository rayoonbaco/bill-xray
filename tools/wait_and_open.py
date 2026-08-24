"""Wait until the local Bill X-Ray server is healthy, then open the requested page."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from urllib.parse import urlsplit, urlunsplit


def health_url_for_target(target_url: str) -> str:
    """Return the server-root health URL for any page on the local app.

    A report target such as http://127.0.0.1:8000/bill/obbba must health-check
    http://127.0.0.1:8000/api/health, not /bill/obbba/api/health.
    """
    parts = urlsplit(target_url)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"Target URL must be absolute: {target_url!r}")
    return urlunsplit((parts.scheme, parts.netloc, "/api/health", "", ""))


def wait_for_health(target_url: str, timeout_seconds: float = 120.0) -> bool:
    health_url = health_url_for_target(target_url)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as response:
                if response.status == 200:
                    payload = json.loads(response.read().decode("utf-8"))
                    if payload.get("status") == "ok":
                        return True
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    target_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/"
    if not wait_for_health(target_url):
        return 1
    webbrowser.open(target_url, new=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

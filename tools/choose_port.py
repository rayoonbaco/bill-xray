"""Choose a free localhost port so an old Bill X-Ray server cannot hijack startup."""
from __future__ import annotations
import socket
import sys

start = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
for port in range(start, start + 21):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            continue
        print(port)
        raise SystemExit(0)
raise SystemExit("No free Bill X-Ray localhost port found in range")

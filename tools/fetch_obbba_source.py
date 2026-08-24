"""Pass 17 helper: fetch official Public Law 119-21 text from GovInfo."""
from __future__ import annotations

import html
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "source_documents" / "obbba.txt"
URL = "https://www.govinfo.gov/content/pkg/PLAW-119publ21/html/PLAW-119publ21.htm"
UA = "Bill-X-Ray/17.0 (public-law evidence prototype)"


def html_to_statute_text(payload: str) -> str:
    body = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", payload)
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?i)</(?:p|div|pre|tr|li|h[1-6])>", "\n", body)
    body = re.sub(r"(?s)<[^>]+>", "", body)
    body = html.unescape(body).replace("\r\n", "\n").replace("\r", "\n")
    body = "\n".join(line.rstrip() for line in body.split("\n"))
    body = re.sub(r"\n{4,}", "\n\n\n", body).strip()
    if "Public Law 119-21" not in body or "H.R. 1" not in body:
        raise ValueError("Downloaded document did not identify itself as Public Law 119-21 / H.R. 1")
    if len(body) < 750_000:
        raise ValueError("Downloaded Public Law 119-21 source appears incomplete")
    return body


def fetch(url: str = URL) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=90) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def ensure_obbba_source(force: bool = False) -> Path:
    if OUT.exists() and OUT.stat().st_size > 750_000 and not force:
        print(f"Official OBBBA source already present: {OUT} ({OUT.stat().st_size:,} bytes)", flush=True)
        return OUT
    print("Fetching official Public Law 119-21 text from U.S. Government Publishing Office (GovInfo)...", flush=True)
    text = html_to_statute_text(fetch())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"Saved official OBBBA source: {OUT} ({OUT.stat().st_size:,} bytes)", flush=True)
    return OUT


if __name__ == "__main__":
    try:
        ensure_obbba_source("--force" in sys.argv)
    except Exception as exc:
        print(f"ERROR: OBBBA source acquisition failed: {exc}", flush=True)
        raise SystemExit(1)

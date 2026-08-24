"""Pass 16 helper: fetch the official ACA public-law text from GovInfo.

The runtime fetch is intentionally separate from Pass 2 ingestion. Pass 2 still ingests
only a local file; this helper acquires that local file from an official source first.
"""
from __future__ import annotations

import html
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "source_documents" / "aca.txt"
URL = "https://www.govinfo.gov/content/pkg/PLAW-111publ148/html/PLAW-111publ148.htm"
UA = "Bill-X-Ray/16.0 (public-law evidence prototype)"


def html_to_statute_text(payload: str) -> str:
    # GovInfo's HTML publication is essentially preformatted statutory text. Preserve
    # line structure while removing HTML markup and decoding entities.
    body = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", payload)
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?i)</(?:p|div|pre|tr|li|h[1-6])>", "\n", body)
    body = re.sub(r"(?s)<[^>]+>", "", body)
    body = html.unescape(body).replace("\r\n", "\n").replace("\r", "\n")
    body = "\n".join(line.rstrip() for line in body.split("\n"))
    body = re.sub(r"\n{4,}", "\n\n\n", body).strip()
    if "Public Law 111-148" not in body or "Patient Protection and Affordable Care Act" not in body:
        raise ValueError("Downloaded document did not identify itself as Public Law 111-148 / ACA")
    if len(body) < 500_000:
        raise ValueError("Downloaded ACA source appears incomplete")
    return body


def fetch(url: str = URL) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=90) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def ensure_aca_source(force: bool = False) -> Path:
    if OUT.exists() and OUT.stat().st_size > 500_000 and not force:
        return OUT
    print("Fetching official ACA text from U.S. Government Publishing Office (GovInfo)...")
    text = html_to_statute_text(fetch())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"Saved official ACA source: {OUT} ({OUT.stat().st_size:,} bytes)")
    return OUT


if __name__ == "__main__":
    try:
        ensure_aca_source("--force" in sys.argv)
    except Exception as exc:
        print(f"ERROR: ACA source acquisition failed: {exc}")
        raise SystemExit(1)

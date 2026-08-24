"""Acquire the official Inflation Reduction Act public-law text from GovInfo."""
from __future__ import annotations

import html
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "source_documents" / "ira.txt"
URL = "https://www.govinfo.gov/content/pkg/PLAW-117publ169/html/PLAW-117publ169.htm"
UA = "Bill-X-Ray/32.0 (curated public-law exhibit)"


def html_to_statute_text(payload: str) -> str:
    body = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", payload)
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?i)</(?:p|div|pre|tr|li|h[1-6])>", "\n", body)
    body = re.sub(r"(?s)<[^>]+>", "", body)
    body = html.unescape(body).replace("\r\n", "\n").replace("\r", "\n")
    body = "\n".join(line.rstrip() for line in body.split("\n"))
    body = re.sub(r"\n{4,}", "\n\n\n", body).strip()
    if not re.search(r"Public Law 117[-–]169", body):
        raise ValueError("Downloaded document did not identify itself as Public Law 117-169")
    if len(body) < 700_000:
        raise ValueError("Downloaded Inflation Reduction Act source appears incomplete")
    return body


def fetch(url: str = URL) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=90) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def ensure_ira_source(force: bool = False) -> Path:
    if OUT.exists() and OUT.stat().st_size > 700_000 and not force:
        return OUT
    print("Fetching official Inflation Reduction Act text from GovInfo...")
    text = html_to_statute_text(fetch())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"Saved official IRA source: {OUT} ({OUT.stat().st_size:,} bytes)")
    return OUT


if __name__ == "__main__":
    try:
        ensure_ira_source("--force" in sys.argv)
    except Exception as exc:
        print(f"ERROR: IRA source acquisition failed: {exc}")
        raise SystemExit(1)

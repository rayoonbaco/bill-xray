"""Pass 22: search and register official GovInfo congressional bill versions.

Discovery is network-facing; analysis remains local-source-first. Search results come from
GovInfo's official API and selected bill text is acquired from predictable GovInfo HTML URLs,
then registered in Bill X-Ray's local manifest before the evidence pipeline runs.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SEARCH_DIR = DATA / "search_results"
DYNAMIC_CATALOG = DATA / "dynamic_bills.json"
SOURCE_MANIFEST = DATA / "source_manifest.json"
SOURCE_DIR = DATA / "source_documents"
SEARCH_ENDPOINT = "https://api.govinfo.gov/search"
UA = "Bill-X-Ray/22.0 (source-first legislative search)"

VERSION_LABELS = {
    "ih": "Introduced in House", "is": "Introduced in Senate", "rh": "Reported in House",
    "rs": "Reported in Senate", "eh": "Engrossed in House", "es": "Engrossed in Senate",
    "eas": "Engrossed Amendment Senate", "eah": "Engrossed Amendment House",
    "enr": "Enrolled Bill", "pcs": "Placed on Calendar Senate", "pch": "Placed on Calendar House",
}
BILL_TYPE_LABELS = {
    "hr": "H.R.", "s": "S.", "hjres": "H.J.Res.", "sjres": "S.J.Res.",
    "hconres": "H.Con.Res.", "sconres": "S.Con.Res.", "hres": "H.Res.", "sres": "S.Res.",
}
PACKAGE_RE = re.compile(r"^BILLS-(?P<congress>\d+)(?P<type>hjres|sjres|hconres|sconres|hres|sres|hr|s)(?P<number>\d+)(?P<version>[a-z0-9]+)$", re.I)


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _api_key() -> str:
    return os.getenv("GOVINFO_API_KEY", "").strip() or "DEMO_KEY"


def _clean_query(query: str) -> str:
    q = " ".join(str(query or "").split()).strip()
    if len(q) < 2:
        raise ValueError("Enter at least two characters to search bills")
    if len(q) > 120:
        q = q[:120]
    return q


def _search_expression(query: str) -> str:
    q = _clean_query(query)
    # Exact bill citations get fielded searching; normal keywords retain GovInfo relevance ranking.
    m = re.search(r"\b(H\.?\s*R\.?|S\.?|H\.?\s*J\.?\s*RES\.?|S\.?\s*J\.?\s*RES\.?)\s*(\d+)\b", q, re.I)
    if m:
        raw = re.sub(r"[^A-Za-z]", "", m.group(1)).lower()
        bt = {"hr": "hr", "s": "s", "hjres": "hjres", "sjres": "sjres"}.get(raw)
        if bt:
            return f"collection:bills billtype:{bt} docnumber:{m.group(2)}"
    safe = q.replace('"', '\\"')
    return f"collection:bills {safe}"


def _parse_package(package_id: str) -> dict:
    m = PACKAGE_RE.match(package_id or "")
    if not m:
        return {}
    d = {k: v.lower() if k in {"type", "version"} else v for k, v in m.groupdict().items()}
    d["bill_number"] = f"{BILL_TYPE_LABELS.get(d['type'], d['type'].upper())} {int(d['number'])}"
    d["version_label"] = VERSION_LABELS.get(d["version"], d["version"].upper())
    return d


def _normalize_result(raw: dict) -> dict | None:
    package_id = str(raw.get("packageId") or raw.get("package_id") or "").strip()
    parsed = _parse_package(package_id)
    if not parsed:
        return None
    title = " ".join(str(raw.get("title") or parsed["bill_number"]).split())
    # GovInfo titles often include the bill citation/version prefix; retain it because it helps identity confirmation.
    return {
        "package_id": package_id,
        "title": title,
        "bill_number": parsed["bill_number"],
        "congress": int(parsed["congress"]),
        "bill_type": parsed["type"],
        "bill_number_numeric": int(parsed["number"]),
        "version_code": parsed["version"],
        "version_label": parsed["version_label"],
        "date_issued": raw.get("dateIssued") or raw.get("date_issued") or raw.get("publishDate") or "",
        "details_url": f"https://www.govinfo.gov/app/details/{package_id}",
        "source_url": f"https://www.govinfo.gov/content/pkg/{package_id}/html/{package_id}.htm",
        "collection": "Congressional Bills",
    }


def _direct_package_id(query: str) -> str | None:
    """Return an exact GovInfo BILLS package ID without using the Search API.

    This is deliberately narrow: only a complete GovInfo package identifier or the
    equivalent Bill X-Ray ``gpo-`` slug is accepted. It does not guess Congress,
    bill version, or package identity from ordinary keywords/citations.
    """
    q = _clean_query(query).strip()
    if q.lower().startswith("gpo-"):
        candidate = "BILLS-" + q[4:]
    else:
        candidate = q
    if not candidate.upper().startswith("BILLS-"):
        return None
    normalized = "BILLS-" + candidate[6:]
    return normalized if _parse_package(normalized) else None


def search_bills(query: str, limit: int = 8) -> dict:
    q = _clean_query(query)
    limit = max(1, min(int(limit), 12))

    # Pass 31.6.2.1a: an exact GovInfo package ID is already an authoritative
    # identity. Registering that identity must not depend on the availability or
    # quota of GovInfo's discovery/search service. Source acquisition remains the
    # official predictable GovInfo package URL and still occurs before analysis.
    direct_package = _direct_package_id(q)
    if direct_package:
        item = _normalize_result({"packageId": direct_package})
        if not item:
            raise ValueError("Invalid GovInfo congressional-bill package identifier")
        token = hashlib.sha256((q + "|" + datetime.now(timezone.utc).isoformat()).encode()).hexdigest()[:18]
        _write_json(SEARCH_DIR / f"{token}.json", {"query": q, "results": [item], "created_at": datetime.now(timezone.utc).isoformat()})
        return {"query": q, "search_token": token, "results": [item], "count": 1, "provider": "GovInfo exact package"}
    payload = {
        "query": _search_expression(q),
        "pageSize": str(max(limit * 2, 10)),
        "offsetMark": "*",
        "sorts": [{"field": "score", "sortOrder": "DESC"}],
        "resultLevel": "package",
    }
    url = SEARCH_ENDPOINT + "?" + urllib.parse.urlencode({"api_key": _api_key()})
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"User-Agent": UA, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode(response.headers.get_content_charset() or "utf-8"))
    except Exception as exc:
        raise RuntimeError("Official GovInfo bill search is temporarily unavailable. Try again in a moment.") from exc
    seen = set()
    results = []
    for raw in body.get("results", []):
        item = _normalize_result(raw)
        if not item or item["package_id"] in seen:
            continue
        seen.add(item["package_id"])
        results.append(item)
        if len(results) >= limit:
            break
    token = hashlib.sha256((q + "|" + datetime.now(timezone.utc).isoformat()).encode()).hexdigest()[:18]
    _write_json(SEARCH_DIR / f"{token}.json", {"query": q, "results": results, "created_at": datetime.now(timezone.utc).isoformat()})
    return {"query": q, "search_token": token, "results": results, "count": len(results), "provider": "GovInfo"}


def _slug_for(package_id: str) -> str:
    return "gpo-" + package_id.lower().replace("bills-", "")


def _load_search_result(search_token: str, package_id: str) -> dict:
    if not re.fullmatch(r"[a-f0-9]{18}", search_token or ""):
        raise ValueError("Search selection expired; please search again")
    payload = _json(SEARCH_DIR / f"{search_token}.json", {})
    for item in payload.get("results", []):
        if item.get("package_id") == package_id:
            return item
    raise ValueError("Selected bill version was not found in this search. Please search again.")


def register_selected_bill(search_token: str, package_id: str) -> dict:
    item = _load_search_result(search_token, package_id)
    bill_id = _slug_for(package_id)
    dynamic = _json(DYNAMIC_CATALOG, {"bills": []})
    bills = [b for b in dynamic.get("bills", []) if b.get("id") != bill_id]
    year = (item.get("date_issued") or "")[:4]
    if not year.isdigit():
        # Congress 119 began in 2025; this approximation is display-only metadata.
        year = str(1787 + 2 * int(item["congress"]))
    record = {
        "id": bill_id,
        "short_title": item["title"],
        "year": int(year),
        "status": "Search result",
        "category": f"{item['bill_number']} · {item['version_label']}",
        "package_id": package_id,
        "congress": item["congress"],
        "bill_number": item["bill_number"],
        "version_code": item["version_code"],
        "version_label": item["version_label"],
        "source_url": item["source_url"],
        "details_url": item["details_url"],
        "dynamic": True,
    }
    bills.insert(0, record)
    dynamic["schema_version"] = "22.0"
    dynamic["bills"] = bills[:100]
    _write_json(DYNAMIC_CATALOG, dynamic)

    manifest = _json(SOURCE_MANIFEST, {"schema_version": "2.0", "bills": []})
    entries = [e for e in manifest.get("bills", []) if e.get("bill_id") != bill_id]
    entries.append({
        "bill_id": bill_id,
        "official_identifier": f"{item['bill_number']}, {item['congress']}th Congress",
        "law_number": "",
        "version": item["version_label"],
        "local_filename": f"{bill_id}.txt",
        "source_url": item["source_url"],
        "package_id": package_id,
    })
    manifest["bills"] = entries
    _write_json(SOURCE_MANIFEST, manifest)
    return record


def ensure_manifest_for_dynamic(meta: dict) -> None:
    """Restore a searched bill's manifest entry after an application-code upgrade."""
    bill_id = meta["id"]
    manifest = _json(SOURCE_MANIFEST, {"schema_version": "2.0", "bills": []})
    entries = [e for e in manifest.get("bills", []) if e.get("bill_id") != bill_id]
    entries.append({
        "bill_id": bill_id,
        "official_identifier": f"{meta.get('bill_number','Selected bill')}, {meta.get('congress','')}th Congress",
        "law_number": "",
        "version": meta.get("version_label", "Selected GovInfo version"),
        "local_filename": f"{bill_id}.txt",
        "source_url": meta["source_url"],
        "package_id": meta.get("package_id", ""),
    })
    manifest["bills"] = entries
    _write_json(SOURCE_MANIFEST, manifest)


def dynamic_bills() -> list[dict]:
    return _json(DYNAMIC_CATALOG, {"bills": []}).get("bills", [])


def selected_bill(bill_id: str) -> dict | None:
    return next((b for b in dynamic_bills() if b.get("id") == bill_id), None)


def html_to_bill_text(payload: str) -> str:
    body = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", payload)
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?i)</(?:p|div|pre|tr|li|h[1-6])>", "\n", body)
    body = re.sub(r"(?s)<[^>]+>", "", body)
    body = html.unescape(body).replace("\r\n", "\n").replace("\r", "\n")
    body = "\n".join(line.rstrip() for line in body.split("\n"))
    body = re.sub(r"\n{4,}", "\n\n\n", body).strip()
    if len(body) < 800:
        raise ValueError("Downloaded bill text appears incomplete")
    return body


def ensure_dynamic_source(bill_id: str, force: bool = False) -> Path:
    meta = selected_bill(bill_id)
    if not meta:
        raise KeyError(f"No registered search bill '{bill_id}'")
    ensure_manifest_for_dynamic(meta)
    out = SOURCE_DIR / f"{bill_id}.txt"
    if out.exists() and out.stat().st_size > 800 and not force:
        return out
    request = urllib.request.Request(meta["source_url"], headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError("Could not download the selected official GovInfo bill text") from exc
    text = html_to_bill_text(payload)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    return out

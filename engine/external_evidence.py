"""Pass 30: official external-evidence retrieval.

The statute remains the primary source. This module adds *separate* authoritative
context lanes from CBO, JCT, and USAspending. External evidence never rewrites a
statutory claim and is never required for release; it is explicitly labeled and
stored with provenance.
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "external_evidence"
UA = "Mozilla/5.0 (compatible; Bill-X-Ray/31.6.1; official external-evidence retrieval)"

CBO_SEARCH = "https://www.cbo.gov/search?search_api_fulltext={query}"
CBO_COST_ESTIMATES = "https://www.cbo.gov/cost-estimates/{chamber}/{number}"
CBO_CONGRESS_XML = "https://www.cbo.gov/rss/{congress}congress-cost-estimates.xml"
JCT_SEARCH = "https://www.jct.gov/?s={query}"
USA_OVER_TIME = "https://api.usaspending.gov/api/v2/search/spending_over_time/"


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[dict] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            text = " ".join(" ".join(self._text).split())
            if text:
                self.links.append({"href": self._href, "text": html.unescape(text)})
            self._href = None
            self._text = []


def _get(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml,text/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")


def _post_json(url: str, payload: dict, timeout: int = 15) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode(r.headers.get_content_charset() or "utf-8"))


def _bill_meta(bill_id: str) -> dict:
    static = json.loads((ROOT / "data" / "bills.json").read_text(encoding="utf-8"))
    dynamic_path = ROOT / "data" / "dynamic_bills.json"
    dynamic = json.loads(dynamic_path.read_text(encoding="utf-8")) if dynamic_path.exists() else {"bills": []}
    bill = next((b for b in dynamic.get("bills", []) + static if b.get("id") == bill_id), None)
    if not bill:
        raise KeyError(f"Unknown bill '{bill_id}'")
    if bill_id == "aca":
        return {**bill, "bill_number": "H.R. 3590", "official_title": "Patient Protection and Affordable Care Act", "congress": 111, "law_number": "Public Law 111-148", "implementation_keyword": "Affordable Care Act"}
    if bill_id == "obbba":
        return {**bill, "bill_number": "H.R. 1", "congress": 119, "law_number": "Public Law 119-21", "implementation_keyword": "One Big Beautiful Bill Act"}
    return bill


def _official_search(provider: str, template: str, query: str, allowed_hosts: tuple[str, ...], limit: int = 5) -> dict:
    url = template.format(query=urllib.parse.quote_plus(query))
    try:
        body = _get(url)
    except Exception as exc:
        return {"provider": provider, "status": "unavailable", "query": query, "search_url": url, "results": [], "note": str(exc)[:180]}
    parser = _LinkParser(); parser.feed(body)
    terms = [t.lower() for t in re.findall(r"[A-Za-z0-9.]+", query) if len(t) > 1]
    out, seen = [], set()
    base = urllib.parse.urlparse(url)
    for link in parser.links:
        href = urllib.parse.urljoin(f"{base.scheme}://{base.netloc}", link["href"])
        host = urllib.parse.urlparse(href).netloc.lower()
        if not any(host == h or host.endswith("." + h) for h in allowed_hosts):
            continue
        text = " ".join(link["text"].split())
        hay = (text + " " + href).lower()
        # CBO/JCT search pages include navigation noise. Require bill-like relevance.
        if terms and not any(t in hay for t in terms):
            continue
        key = (text, href)
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": text[:220], "url": href, "source": provider})
        if len(out) >= limit:
            break
    return {
        "provider": provider,
        "status": "found" if out else "no_match",
        "query": query,
        "search_url": url,
        "results": out,
        "note": "Official-site search results; absence of a match is not evidence that no estimate exists.",
    }



def _normalize_bill_number(value: str) -> dict | None:
    """Return CBO's documented predictable bill-number path components."""
    raw = " ".join(str(value or "").upper().replace("–", "-").split())
    m = re.fullmatch(r"(H\.?\s*R\.?|S\.?|H\.?\s*J\.?\s*RES\.?|S\.?\s*J\.?\s*RES\.?|H\.?\s*CON\.?\s*RES\.?|S\.?\s*CON\.?\s*RES\.?)\s*(\d+)", raw)
    if not m:
        return None
    kind = re.sub(r"[^A-Z]", "", m.group(1))
    chamber_map = {
        "HR": "hr", "S": "s", "HJRES": "hjres", "SJRES": "sjres",
        "HCONRES": "hconres", "SCONRES": "sconres",
    }
    chamber = chamber_map.get(kind)
    if not chamber:
        return None
    return {"chamber": chamber, "number": m.group(2), "canonical": f"{m.group(1).replace(' ', '')} {m.group(2)}"}


def _norm_text(value: str) -> str:
    value = html.unescape(str(value or "")).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _title_tokens(value: str) -> set[str]:
    stop = {"the", "a", "an", "of", "and", "for", "to", "in", "on", "act", "bill", "estimated", "estimate", "budgetary", "effects", "cost"}
    return {w for w in _norm_text(value).split() if len(w) > 2 and w not in stop}


def _candidate_score(title: str, meta: dict) -> tuple[float, list[str]]:
    norm = _norm_text(title)
    bill_number = str(meta.get("bill_number") or "").strip()
    compact_bill = _norm_text(bill_number)
    official_title = str(meta.get("official_title") or meta.get("short_title") or meta.get("title") or "").strip()
    short_title = str(meta.get("short_title") or meta.get("title") or "").strip()
    reasons: list[str] = []
    score = 0.0
    if compact_bill and compact_bill in norm:
        score += 0.45; reasons.append("exact bill number in CBO title")
    for label, weight in ((official_title, 0.50), (short_title, 0.42)):
        nlabel = _norm_text(label)
        if nlabel and nlabel in norm:
            score += weight; reasons.append(f"title match: {label}")
            break
        toks = _title_tokens(label)
        if toks:
            overlap = len(toks & set(norm.split())) / len(toks)
            if overlap >= 0.75:
                score += weight * overlap; reasons.append(f"strong title-token overlap ({overlap:.2f})")
                break
    return min(score, 1.0), reasons


def _cbo_candidates_from_html(body: str, base_url: str, meta: dict) -> list[dict]:
    parser = _LinkParser(); parser.feed(body)
    out, seen = [], set()
    for link in parser.links:
        href = urllib.parse.urljoin(base_url, link.get("href") or "")
        host = urllib.parse.urlparse(href).netloc.lower()
        if host not in {"cbo.gov", "www.cbo.gov"}:
            continue
        if "/publication/" not in urllib.parse.urlparse(href).path:
            continue
        title = " ".join(str(link.get("text") or "").split())
        if not title or href in seen:
            continue
        seen.add(href)
        score, reasons = _candidate_score(title, meta)
        out.append({"title": title[:260], "url": href, "source": "CBO", "identity_confidence": round(score, 3), "identity_basis": reasons})
    return sorted(out, key=lambda r: (-r["identity_confidence"], r["title"]))


def _cbo_candidates_from_xml(body: str, meta: dict) -> list[dict]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    out, seen = [], set()
    for node in root.iter():
        if node.tag.split("}")[-1].lower() not in {"item", "entry"}:
            continue
        title = ""; href = ""; date = ""
        for child in node.iter():
            tag = child.tag.split("}")[-1].lower()
            text = " ".join((child.text or "").split())
            if tag == "title" and text and not title:
                title = text
            elif tag in {"link", "guid"}:
                candidate = child.attrib.get("href") or text
                if candidate and "cbo.gov" in candidate and not href:
                    href = candidate
            elif tag in {"pubdate", "date", "published", "dc:date"} and text and not date:
                date = text
        if not title or not href or href in seen:
            continue
        seen.add(href)
        score, reasons = _candidate_score(title, meta)
        out.append({"title": title[:260], "url": href, "source": "CBO", "date": date or None, "identity_confidence": round(score, 3), "identity_basis": reasons})
    return sorted(out, key=lambda r: (-r["identity_confidence"], r["title"]))


def _cbo_discovery(meta: dict, limit: int = 5) -> dict:
    """CBO-specific retrieval using CBO's predictable bill URL, then congress XML, then site search."""
    bill_number = str(meta.get("bill_number") or "").strip()
    title = str(meta.get("official_title") or meta.get("short_title") or meta.get("title") or "").strip()
    congress = meta.get("congress")
    diagnostics: list[dict] = []
    candidates: list[dict] = []
    normalized = _normalize_bill_number(bill_number)

    if normalized:
        url = CBO_COST_ESTIMATES.format(chamber=normalized["chamber"], number=normalized["number"])
        try:
            body = _get(url)
            found = _cbo_candidates_from_html(body, url, meta)
            diagnostics.append({"method": "predictable_bill_url", "url": url, "status": "ok", "candidate_count": len(found)})
            candidates.extend(found)
        except Exception as exc:
            diagnostics.append({"method": "predictable_bill_url", "url": url, "status": "network_or_response_failure", "detail": str(exc)[:180]})

    if congress:
        url = CBO_CONGRESS_XML.format(congress=int(congress))
        try:
            body = _get(url)
            found = _cbo_candidates_from_xml(body, meta)
            diagnostics.append({"method": "congress_xml", "url": url, "status": "ok", "candidate_count": len(found)})
            candidates.extend(found)
        except Exception as exc:
            diagnostics.append({"method": "congress_xml", "url": url, "status": "network_or_response_failure", "detail": str(exc)[:180]})

    # Deduplicate, retaining the strongest identity score for each canonical CBO URL.
    dedup: dict[str, dict] = {}
    for row in candidates:
        if not row.get("url"):
            continue
        prior = dedup.get(row["url"])
        if prior is None or row.get("identity_confidence", 0) > prior.get("identity_confidence", 0):
            dedup[row["url"]] = row
    ranked = sorted(dedup.values(), key=lambda r: (-r.get("identity_confidence", 0), r.get("title", "")))
    has_title_signal = bool(_title_tokens(title))
    threshold = 0.65 if has_title_signal else 0.45
    accepted = [r for r in ranked if r.get("identity_confidence", 0) >= threshold]

    query = f"{bill_number} {title}".strip()
    search_url = CBO_SEARCH.format(query=urllib.parse.quote_plus(query))
    if not accepted:
        generic = _official_search("CBO", CBO_SEARCH, query, ("cbo.gov", "www.cbo.gov"), limit=10)
        diagnostics.append({"method": "site_search", "url": generic.get("search_url"), "status": generic.get("status"), "candidate_count": len(generic.get("results", []))})
        rescored = []
        for row in generic.get("results", []):
            score, reasons = _candidate_score(row.get("title", ""), meta)
            if score >= threshold:
                rescored.append({**row, "identity_confidence": round(score, 3), "identity_basis": reasons})
        accepted = sorted(rescored, key=lambda r: (-r.get("identity_confidence", 0), r.get("title", "")))

    if accepted:
        return {
            "provider": "CBO", "status": "found", "query": query, "search_url": search_url,
            "results": accepted[:limit], "selected": accepted[0], "diagnostics": diagnostics,
            "note": "Official CBO material matched by bill identity. CBO estimates are external context, not statutory text.",
        }
    attempted_ok = any(d.get("status") == "ok" for d in diagnostics)
    return {
        "provider": "CBO", "status": "no_match" if attempted_ok else "unavailable", "query": query,
        "search_url": search_url, "results": [], "diagnostics": diagnostics,
        "note": "CBO context could not be verified automatically during this build. Absence of a verified match is not evidence that CBO has no analysis.",
    }

def _implementation_keyword(meta: dict) -> str | None:
    explicit = " ".join(str(meta.get("implementation_keyword") or "").split()).strip()
    if explicit:
        return explicit
    title = " ".join(str(meta.get("short_title") or meta.get("title") or "").split()).strip()
    # Avoid searching generic bill citations/titles that would create meaningless award totals.
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]+", title) if w.lower() not in {"act", "bill", "resolution", "amendment", "of", "the", "and", "for", "to"}]
    if len(words) < 3:
        return None
    return " ".join(words[:8])


def _usaspending_context(meta: dict) -> dict:
    keyword = _implementation_keyword(meta)
    if not keyword:
        return {"provider": "USAspending", "status": "not_attempted", "results": [], "note": "No sufficiently specific implementation keyword was available."}
    start_year = max(2008, int(meta.get("year") or 2008))
    end_year = datetime.now(timezone.utc).year
    payload = {
        "group": "fiscal_year",
        "filters": {
            "keywords": [keyword],
            "time_period": [{"start_date": f"{start_year}-01-01", "end_date": f"{end_year}-12-31"}],
            "award_type_codes": ["A", "B", "C", "D", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11"],
        },
    }
    try:
        body = _post_json(USA_OVER_TIME, payload)
    except Exception as exc:
        return {"provider": "USAspending", "status": "unavailable", "keyword": keyword, "results": [], "note": str(exc)[:180]}
    rows = body.get("results") if isinstance(body, dict) else []
    rows = rows if isinstance(rows, list) else []
    total = 0.0
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        amount = row.get("aggregated_amount")
        if amount is None:
            amount = row.get("amount") or row.get("obligations") or row.get("federal_action_obligation") or 0
        try:
            amount = float(amount or 0)
        except (TypeError, ValueError):
            amount = 0.0
        total += amount
        normalized.append({"time_period": row.get("time_period") or row.get("fiscal_year") or row.get("date_range"), "amount": amount})
    return {
        "provider": "USAspending",
        "status": "found" if normalized else "no_match",
        "keyword": keyword,
        "query_url": "https://www.usaspending.gov/search",
        "total_related_obligations": round(total, 2),
        "results": normalized[-8:],
        "note": "Keyword-correlated federal award activity. This is implementation context, not proof that an award was caused by this bill.",
    }


def collect_external_evidence(bill_id: str) -> dict:
    meta = _bill_meta(bill_id)
    bill_number = str(meta.get("bill_number") or "").strip()
    title = str(meta.get("short_title") or "").strip()
    query = f"{bill_number} {title}".strip()
    cbo = _cbo_discovery(meta)
    jct = _official_search("JCT", JCT_SEARCH, query, ("jct.gov", "www.jct.gov"))
    spending = _usaspending_context(meta)
    payload = {
        "schema_version": "31.6.1",
        "bill_id": bill_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "identity": {"bill_number": bill_number, "title": title, "congress": meta.get("congress"), "law_number": meta.get("law_number")},
        "lanes": {"cbo": cbo, "jct": jct, "usaspending": spending},
        "rules": [
            "External evidence never rewrites or substitutes for the statutory text.",
            "CBO/JCT estimates describe expected budget or revenue effects when a matching official estimate is available.",
            "USAspending keyword matches are contextual award activity, not causal attribution to the bill.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{bill_id}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def external_status(bill_id: str) -> dict:
    path = OUT_DIR / f"{bill_id}.json"
    if not path.exists():
        return {"bill_id": bill_id, "status": "not_generated", "lanes": {}}
    return json.loads(path.read_text(encoding="utf-8"))

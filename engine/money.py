"""Pass 6: source-bound monetary provision extraction for Bill X-Ray.

The money extractor identifies explicit fiscal mechanics in verified Pass 4 section
anchors. It does not estimate macroeconomic effects, score policy, or infer a net
budget impact. A finding says only what the statutory language explicitly does or
references: appropriations, rescissions, taxes, credits, grants, subsidies, fees,
loans, transfers, or other revenue/spending mechanics.

Authoritative external fiscal estimates (CBO/JCT/etc.) belong to later synthesis.
This pass creates the statutory evidence layer those estimates can be joined to.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from engine import citations

ROOT = Path(__file__).resolve().parents[1]
ANCHOR_DIR = ROOT / "data" / "citation_anchors"
MONEY_DIR = ROOT / "data" / "money"
PROVING_GROUND_BILLS = ("aca", "obbba")
EXTRACTOR_VERSION = "30.1-amount-provenance"

_MONEY_SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("appropriation", re.compile(r"\bappropriat(?:e|ed|es|ing|ion|ions)\b|\bamounts? (?:is|are) hereby appropriated\b", re.I)),
    ("rescission", re.compile(r"\brescind(?:ed|s|ing)?\b|\brescission\b", re.I)),
    ("tax", re.compile(r"\btax(?:es|able|ation)?\b|\binternal revenue code\b", re.I)),
    ("credit", re.compile(r"\b(?:tax\s+)?credit(?:s)?\b", re.I)),
    ("grant", re.compile(r"\bgrant(?:s)?\b", re.I)),
    ("subsidy", re.compile(r"\bsubsid(?:y|ies|ize|ized|izes)\b", re.I)),
    ("revenue", re.compile(r"\brevenue(?:s)?\b|\breceipts?\b", re.I)),
    ("fee", re.compile(r"\bfee(?:s)?\b|\bassessment(?:s)?\b", re.I)),
    ("loan", re.compile(r"\bloan(?:s)?\b|\bloan guarantee(?:s)?\b", re.I)),
    ("transfer", re.compile(r"\btransfer(?:red|s|ring)?\b", re.I)),
    ("funding", re.compile(r"\bfund(?:ing|s)?\b|\bavailable to carry out\b", re.I)),
)

_DOLLAR_RE = re.compile(
    r"(?P<raw>\$\s*(?P<number>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?P<scale>trillion|billion|million|thousand)?)",
    re.I,
)
_PERCENT_RE = re.compile(r"(?P<raw>\b\d+(?:\.\d+)?\s*percent\b|\b\d+(?:\.\d+)?%)", re.I)
_FY_RE = re.compile(r"\bfiscal year(?:s)?\s+\d{4}(?:\s+through\s+\d{4})?\b|\bFY\s*\d{4}\b", re.I)
_AVAILABILITY_RE = re.compile(
    r"\b(?:to remain available until expended|until expended|for each of fiscal years?[^.;]*|for fiscal years?[^.;]*|for the period beginning[^.;]*)",
    re.I,
)


@dataclass(frozen=True)
class MoneyAmount:
    raw: str
    amount_usd: str
    # Pass 30.1: canonical amount-level provenance. Every dollar amount carries
    # the clause/sentence in which it appears so downstream stages never have
    # to infer its meaning from a truncated section excerpt.
    context_excerpt: str = ""
    context_kind: str = "unknown"
    local_categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class MoneyFinding:
    schema_version: str
    extractor_version: str
    bill_id: str
    anchor_id: str
    segment_id: str
    section_label: str
    status: str
    claim_class: str
    confidence: float
    categories: list[str]
    amounts: list[MoneyAmount]
    percentages: list[str]
    fiscal_direction: str
    operative_excerpt: str
    timing: list[str]
    location_marker: str
    document_ref: str
    source_url: str
    source_sha256: str
    text_sha256: str
    review_reason: str | None


@dataclass(frozen=True)
class MoneyIndex:
    schema_version: str
    bill_id: str
    extractor_version: str
    source_sha256: str
    finding_count: int
    quantified_count: int
    context_review_count: int
    findings: list[MoneyFinding]


def _compact(text: str) -> str:
    return " ".join(text.split())


def _body(exact_text: str) -> str:
    lines = [line.strip() for line in exact_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [line for line in lines if line]
    if lines and re.match(r"^SEC(?:TION)?\.?\s+\S+", lines[0], re.I):
        lines = lines[1:]
    return _compact(" ".join(lines))


def _categories(text: str) -> list[str]:
    return [label for label, pattern in _MONEY_SIGNALS if pattern.search(text)]


def _amount_context(text: str, start: int, end: int) -> str:
    """Return the smallest useful clause/sentence containing one dollar amount."""
    left_candidates = [text.rfind(mark, 0, start) for mark in (".", ";", "\n")]
    left = max(left_candidates) + 1
    right_candidates = [x for x in (text.find(mark, end) for mark in (".", ";", "\n")) if x >= 0]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    return _compact(text[left:right].strip())


_CONTEXTUAL_AMOUNT_RE = re.compile(
    r"\b(?:project(?:ed|ion|ions)?|forecast(?:ed|s)?|estimate(?:d|s)?|"
    r"expected\s+to|anticipated\s+to|national\s+(?:health\s+)?spending|"
    r"market\s+size|economic\s+output)\b", re.I
)


def _amount_context_kind(context: str) -> str:
    if _CONTEXTUAL_AMOUNT_RE.search(context or ""):
        return "context_projection"
    return "statutory_clause"


def _amounts(text: str) -> list[MoneyAmount]:
    values: list[MoneyAmount] = []
    scale_map = {
        "": Decimal(1),
        "thousand": Decimal(1_000),
        "million": Decimal(1_000_000),
        "billion": Decimal(1_000_000_000),
        "trillion": Decimal(1_000_000_000_000),
    }
    for match in _DOLLAR_RE.finditer(text):
        raw = _compact(match.group("raw"))
        number = match.group("number").replace(",", "")
        scale = (match.group("scale") or "").lower()
        try:
            amount = Decimal(number) * scale_map[scale]
        except (InvalidOperation, KeyError):
            continue
        normalized = format(amount.quantize(Decimal("1")), "f")
        context = _amount_context(text, match.start(), match.end())
        local_cats = tuple(_categories(context))
        item = MoneyAmount(
            raw=raw,
            amount_usd=normalized,
            context_excerpt=context,
            context_kind=_amount_context_kind(context),
            local_categories=local_cats,
        )
        if item not in values:
            values.append(item)
    return values


def _timing(text: str) -> list[str]:
    found: list[str] = []
    for pattern in (_FY_RE, _AVAILABILITY_RE):
        for match in pattern.finditer(text):
            value = _compact(match.group(0)).strip(" ,")
            if value and value.lower() not in {x.lower() for x in found}:
                found.append(value)
    return found


def _direction(text: str, categories: list[str]) -> str:
    # Direction is deliberately textual, not a net-budget conclusion.
    if "rescission" in categories:
        return "funding_reduction"
    if re.search(r"\b(?:impose|increase|raise|collect)\w*\b[^.;]{0,80}\b(?:tax|fee|assessment|revenue)\b", text, re.I):
        return "government_receipt"
    if re.search(r"\b(?:reduce|repeal|eliminate|decrease)\w*\b[^.;]{0,80}\b(?:tax|fee|assessment)\b", text, re.I):
        return "receipt_reduction"
    if any(cat in categories for cat in ("appropriation", "grant", "subsidy", "loan", "transfer", "funding")):
        return "funding_or_authority"
    if any(cat in categories for cat in ("tax", "credit", "revenue", "fee")):
        return "revenue_or_tax_mechanic"
    return "unspecified"


def _operative_excerpt(text: str, limit: int = 700) -> str:
    compact = _compact(text)
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def extract_anchor_payload(anchor: dict) -> MoneyFinding | None:
    required = (
        "anchor_id", "bill_id", "segment_id", "section_label", "location_marker",
        "document_ref", "source_url", "source_sha256", "text_sha256", "exact_text",
    )
    missing = [key for key in required if key not in anchor]
    if missing:
        raise ValueError(f"Verified anchor is missing required fields: {', '.join(missing)}")
    if not anchor.get("verified"):
        raise ValueError("Money extraction requires a verified Pass 4 anchor")

    text = _body(str(anchor["exact_text"]))
    cats = _categories(text)
    amounts = _amounts(text)
    percentages = [m.group("raw") for m in _PERCENT_RE.finditer(text)]

    # Dollar figures alone are candidates because some appropriations tables omit a
    # nearby keyword. Conversely, a keyword with no amount is still money-relevant,
    # but it is marked for fiscal-context review rather than assigned an invented sum.
    if not cats and not amounts:
        return None

    status = "extracted" if amounts else "needs_fiscal_context"
    confidence = 0.98 if amounts and cats else (0.91 if amounts else 0.84)
    review_reason = None
    if not amounts:
        review_reason = "Money-related statutory language was found, but this anchor contains no explicit dollar amount."
    elif not cats:
        review_reason = "A dollar amount was found without a recognized fiscal-mechanic keyword; preserve for review."
        status = "needs_fiscal_context"
        confidence = 0.82

    return MoneyFinding(
        schema_version="30.1",
        extractor_version=EXTRACTOR_VERSION,
        bill_id=str(anchor["bill_id"]),
        anchor_id=str(anchor["anchor_id"]),
        segment_id=str(anchor["segment_id"]),
        section_label=str(anchor["section_label"]),
        status=status,
        claim_class="TEXT",
        confidence=confidence,
        categories=cats or ["unclassified_money_amount"],
        amounts=amounts,
        percentages=list(dict.fromkeys(percentages)),
        fiscal_direction=_direction(text, cats),
        operative_excerpt=_operative_excerpt(text),
        timing=_timing(text),
        location_marker=str(anchor["location_marker"]),
        document_ref=str(anchor["document_ref"]),
        source_url=str(anchor["source_url"]),
        source_sha256=str(anchor["source_sha256"]),
        text_sha256=str(anchor["text_sha256"]),
        review_reason=review_reason,
    )


def extract_bill(bill_id: str, *, write: bool = True) -> MoneyIndex:
    anchor_path = ANCHOR_DIR / f"{bill_id}.json"
    if not anchor_path.exists():
        raise FileNotFoundError(f"Citation anchors not found: {anchor_path}")
    anchor_index = json.loads(anchor_path.read_text(encoding="utf-8"))
    findings: list[MoneyFinding] = []

    for anchor in anchor_index.get("anchors", []):
        # Money evidence is section-bound in V1. Structural title/division anchors can
        # duplicate entire child sections and would otherwise double count findings.
        if anchor.get("kind") != "section":
            continue
        verified = citations.resolve_anchor(bill_id, str(anchor["anchor_id"]))
        finding = extract_anchor_payload(verified)
        if finding is not None:
            findings.append(finding)

    result = MoneyIndex(
        schema_version="30.1",
        bill_id=bill_id,
        extractor_version=EXTRACTOR_VERSION,
        source_sha256=str(anchor_index.get("source_sha256", "")),
        finding_count=len(findings),
        quantified_count=sum(bool(item.amounts) for item in findings),
        context_review_count=sum(item.status != "extracted" for item in findings),
        findings=findings,
    )
    if write:
        MONEY_DIR.mkdir(parents=True, exist_ok=True)
        (MONEY_DIR / f"{bill_id}.json").write_text(
            json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return result


def extract_available(*, write: bool = True) -> dict[str, list[str]]:
    extracted: list[str] = []
    missing_anchors: list[str] = []
    failed: list[str] = []
    for bill_id in PROVING_GROUND_BILLS:
        if not (ANCHOR_DIR / f"{bill_id}.json").exists():
            missing_anchors.append(bill_id)
            continue
        try:
            extract_bill(bill_id, write=write)
            extracted.append(bill_id)
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            failed.append(bill_id)
    return {"extracted": extracted, "missing_anchors": missing_anchors, "failed": failed}


def money_status() -> dict[str, dict]:
    status: dict[str, dict] = {}
    for bill_id in PROVING_GROUND_BILLS:
        anchor_path = ANCHOR_DIR / f"{bill_id}.json"
        money_path = MONEY_DIR / f"{bill_id}.json"
        finding_count = quantified_count = context_review_count = 0
        source_fingerprint_matches = False
        if money_path.exists():
            try:
                payload = json.loads(money_path.read_text(encoding="utf-8"))
                finding_count = int(payload.get("finding_count", 0))
                quantified_count = int(payload.get("quantified_count", 0))
                context_review_count = int(payload.get("context_review_count", 0))
                if anchor_path.exists():
                    anchors = json.loads(anchor_path.read_text(encoding="utf-8"))
                    source_fingerprint_matches = payload.get("source_sha256") == anchors.get("source_sha256")
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        status[bill_id] = {
            "anchors_present": anchor_path.exists(),
            "money_artifact_present": money_path.exists(),
            "finding_count": finding_count,
            "quantified_count": quantified_count,
            "context_review_count": context_review_count,
            "source_fingerprint_matches": source_fingerprint_matches,
        }
    return status


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract source-bound Bill X-Ray monetary provisions")
    parser.add_argument("bill_id", nargs="?", help="bill id, e.g. aca or obbba")
    parser.add_argument("--status", action="store_true", help="show money-extractor readiness")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.status:
        print(json.dumps(money_status(), indent=2))
        return 0
    if args.bill_id:
        result = extract_bill(args.bill_id)
        print(
            f"Extracted {result.finding_count:,} money provisions for {result.bill_id}; "
            f"{result.quantified_count:,} contain explicit dollar amounts"
        )
        return 0

    result = extract_available()
    print(json.dumps(result, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

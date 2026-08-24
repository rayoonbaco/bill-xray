"""Pass 7: source-bound government power / authority extraction for Bill X-Ray.

This module identifies explicit statutory changes in governmental authority from
verified Pass 4 section anchors. It does not decide whether a power is wise,
constitutional, excessive, weak, or likely to be used. It records the legal
mechanic the text itself establishes so later expert and referee passes can reason
from a clean evidence layer.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from engine import citations

ROOT = Path(__file__).resolve().parents[1]
ANCHOR_DIR = ROOT / "data" / "citation_anchors"
POWER_DIR = ROOT / "data" / "power"
PROVING_GROUND_BILLS = ("aca", "obbba")
EXTRACTOR_VERSION = "7.0-statutory-floor"

# These signals are intentionally textual. They identify an authority mechanic,
# not a constitutional conclusion or an estimate of institutional significance.
_AUTHORITY_SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("rulemaking", re.compile(r"\b(?:promulgate|prescribe|issue|adopt)\w*\b[^.;]{0,100}\b(?:rule|rules|regulation|regulations|standards?)\b|\brulemaking\b", re.I)),
    ("enforcement", re.compile(r"\b(?:enforce|enforcement|investigate|inspection|subpoena|civil penalty|penalty|injunction|seize|forfeit|audit)\w*\b", re.I)),
    ("waiver_or_exemption", re.compile(r"\b(?:waive|waiver|exempt|exemption|exception)\w*\b", re.I)),
    ("prohibition_or_limit", re.compile(r"\b(?:shall not|may not|must not|prohibit(?:ed|s|ion)?|barred from|restriction|limit(?:ed|ation)?)\b", re.I)),
    ("delegated_discretion", re.compile(r"\b(?:may|is authorized to|are authorized to|at the discretion of)\b", re.I)),
    ("mandatory_duty", re.compile(r"\b(?:shall|must|is required to|are required to)\b", re.I)),
    ("oversight_or_reporting", re.compile(r"\b(?:submit|report|reporting|review|monitor|oversight|audit)\w*\b[^.;]{0,100}\b(?:Congress|committee|Comptroller General|Inspector General|Secretary|agency|department)\b|\breport to Congress\b", re.I)),
    ("appointment_or_structure", re.compile(r"\b(?:appoint|appointment|remove|removal|there is established|is established|establish(?:es|ed|ing)?)\b", re.I)),
    ("federal_state_relationship", re.compile(r"\b(?:preempt|preemption|supersede|State law|State laws|state law|state laws|federal law|Federal law|State shall|States shall)\b", re.I)),
    ("emergency_authority", re.compile(r"\b(?:emergency authority|during a national emergency|upon declaration of an emergency|emergency powers?)\b", re.I)),
)

_GOV_ACTOR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bthe President\b", re.I),
    re.compile(r"\bthe Vice President\b", re.I),
    re.compile(r"\bthe Attorney General\b", re.I),
    re.compile(r"\bthe Secretary(?: of [A-Z][A-Za-z& ,\-]+)?\b", re.I),
    re.compile(r"\bthe Administrator(?: of [A-Z][A-Za-z& ,\-]+)?\b", re.I),
    re.compile(r"\bthe Director(?: of [A-Z][A-Za-z& ,\-]+)?\b", re.I),
    re.compile(r"\bthe Commissioner(?: of [A-Z][A-Za-z& ,\-]+)?\b", re.I),
    re.compile(r"\bthe Comptroller General\b", re.I),
    re.compile(r"\bthe Inspector General\b", re.I),
    re.compile(r"\bthe Commission\b", re.I),
    re.compile(r"\bthe Board\b", re.I),
    re.compile(r"\bthe Department(?: of [A-Z][A-Za-z& ,\-]+)?\b", re.I),
    re.compile(r"\bthe Agency\b", re.I),
    re.compile(r"\ba State\b", re.I),
    re.compile(r"\bthe State\b", re.I),
    re.compile(r"\bStates\b", re.I),
    re.compile(r"\bCongress\b", re.I),
)

_CROSS_REFERENCE_RE = re.compile(r"\b(?:section|subsection|paragraph|clause)\s+[0-9A-Za-z()\-]+\s+of\b", re.I)


@dataclass(frozen=True)
class AuthorityFinding:
    schema_version: str
    extractor_version: str
    bill_id: str
    anchor_id: str
    segment_id: str
    section_label: str
    status: str
    claim_class: str
    confidence: float
    authority_types: list[str]
    actors: list[str]
    modality: list[str]
    authority_direction: str
    operative_excerpt: str
    location_marker: str
    document_ref: str
    source_url: str
    source_sha256: str
    text_sha256: str
    review_reason: str | None


@dataclass(frozen=True)
class AuthorityIndex:
    schema_version: str
    bill_id: str
    extractor_version: str
    source_sha256: str
    finding_count: int
    review_count: int
    findings: list[AuthorityFinding]


def _compact(text: str) -> str:
    return " ".join(text.split())


def _body(exact_text: str) -> str:
    lines = [line.strip() for line in exact_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [line for line in lines if line]
    if lines and re.match(r"^SEC(?:TION)?\.?\s+\S+", lines[0], re.I):
        lines = lines[1:]
    return _compact(" ".join(lines))


def _authority_types(text: str) -> list[str]:
    return [label for label, pattern in _AUTHORITY_SIGNALS if pattern.search(text)]


def _actors(text: str) -> list[str]:
    found: list[str] = []
    for pattern in _GOV_ACTOR_PATTERNS:
        for match in pattern.finditer(text):
            value = _compact(match.group(0)).strip(" ,.;:")
            if value and value.lower() not in {item.lower() for item in found}:
                found.append(value)
    return found[:8]


def _modality(text: str) -> list[str]:
    checks = (
        ("must", r"\b(?:shall|must|is required to|are required to)\b"),
        ("may", r"\b(?:may|is authorized to|are authorized to)\b"),
        ("must_not", r"\b(?:shall not|must not)\b"),
        ("may_not", r"\bmay not\b"),
    )
    return [label for label, pattern in checks if re.search(pattern, text, re.I)]


def _direction(types: list[str], text: str) -> str:
    # Direction is deliberately mechanical. It does not say whether total state
    # power grew or shrank across the whole statute.
    if "appointment_or_structure" in types and re.search(r"\b(?:there is established|is established|establish(?:es|ed)?)\b", text, re.I):
        return "creates_or_structures_authority"
    if "prohibition_or_limit" in types and not any(t in types for t in ("delegated_discretion", "rulemaking", "enforcement", "waiver_or_exemption")):
        return "limits_authority_or_conduct"
    if "waiver_or_exemption" in types:
        return "creates_or_changes_exception_power"
    if "rulemaking" in types:
        return "assigns_rulemaking_authority"
    if "enforcement" in types:
        return "assigns_enforcement_authority"
    if "federal_state_relationship" in types:
        return "changes_federal_state_rule"
    if "delegated_discretion" in types:
        return "assigns_discretion"
    if "mandatory_duty" in types or "oversight_or_reporting" in types:
        return "imposes_government_duty"
    return "authority_mechanic_unspecified"


def _excerpt(text: str, limit: int = 700) -> str:
    compact = _compact(text)
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def extract_anchor_payload(anchor: dict) -> AuthorityFinding | None:
    required = (
        "anchor_id", "bill_id", "segment_id", "section_label", "location_marker",
        "document_ref", "source_url", "source_sha256", "text_sha256", "exact_text",
    )
    missing = [key for key in required if key not in anchor]
    if missing:
        raise ValueError(f"Verified anchor is missing required fields: {', '.join(missing)}")
    if not anchor.get("verified"):
        raise ValueError("Power extraction requires a verified Pass 4 anchor")

    text = _body(str(anchor["exact_text"]))
    if not text:
        return None

    types = _authority_types(text)
    if not types:
        return None

    actors = _actors(text)
    modality = _modality(text)
    review_reasons: list[str] = []

    # Broad words like "may" occur in private-rights provisions too. If there is no
    # identifiable government actor and no intrinsically governmental mechanic,
    # preserve the candidate but refuse to turn it into a clean power claim.
    intrinsic = {
        "rulemaking", "enforcement", "appointment_or_structure",
        "federal_state_relationship", "oversight_or_reporting", "emergency_authority",
    }
    if not actors and not intrinsic.intersection(types):
        review_reasons.append("No government actor is explicit in the anchored section.")
    if _CROSS_REFERENCE_RE.search(text):
        review_reasons.append("Cross-reference language may change the scope of the authority mechanic.")

    status = "needs_legal_context" if review_reasons else "extracted"
    confidence = 0.82 if status == "needs_legal_context" else 0.96

    return AuthorityFinding(
        schema_version="7.0",
        extractor_version=EXTRACTOR_VERSION,
        bill_id=str(anchor["bill_id"]),
        anchor_id=str(anchor["anchor_id"]),
        segment_id=str(anchor["segment_id"]),
        section_label=str(anchor["section_label"]),
        status=status,
        claim_class="TEXT",
        confidence=confidence,
        authority_types=types,
        actors=actors,
        modality=modality,
        authority_direction=_direction(types, text),
        operative_excerpt=_excerpt(text),
        location_marker=str(anchor["location_marker"]),
        document_ref=str(anchor["document_ref"]),
        source_url=str(anchor["source_url"]),
        source_sha256=str(anchor["source_sha256"]),
        text_sha256=str(anchor["text_sha256"]),
        review_reason=" ".join(review_reasons) if review_reasons else None,
    )


def _load_verified_section_anchors(bill_id: str) -> list[dict]:
    index_path = ANCHOR_DIR / f"{bill_id}.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Citation anchors not found: {index_path}")
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    resolved: list[dict] = []
    for anchor in payload.get("anchors", []):
        if anchor.get("kind") != "section":
            continue
        resolved.append(citations.resolve_anchor(bill_id, str(anchor["anchor_id"])))
    return resolved


def extract_bill(bill_id: str, *, write: bool = True) -> AuthorityIndex:
    anchors = _load_verified_section_anchors(bill_id)
    findings: list[AuthorityFinding] = []
    source_sha = ""
    for anchor in anchors:
        source_sha = source_sha or str(anchor.get("source_sha256", ""))
        finding = extract_anchor_payload(anchor)
        if finding is not None:
            findings.append(finding)

    result = AuthorityIndex(
        schema_version="7.0",
        bill_id=bill_id,
        extractor_version=EXTRACTOR_VERSION,
        source_sha256=source_sha,
        finding_count=len(findings),
        review_count=sum(1 for item in findings if item.status == "needs_legal_context"),
        findings=findings,
    )
    if write:
        POWER_DIR.mkdir(parents=True, exist_ok=True)
        (POWER_DIR / f"{bill_id}.json").write_text(
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


def power_status() -> dict[str, dict]:
    status: dict[str, dict] = {}
    for bill_id in PROVING_GROUND_BILLS:
        anchor_path = ANCHOR_DIR / f"{bill_id}.json"
        power_path = POWER_DIR / f"{bill_id}.json"
        finding_count = 0
        review_count = 0
        if power_path.exists():
            try:
                payload = json.loads(power_path.read_text(encoding="utf-8"))
                finding_count = int(payload.get("finding_count", 0))
                review_count = int(payload.get("review_count", 0))
            except (OSError, ValueError, json.JSONDecodeError):
                finding_count = 0
                review_count = 0
        status[bill_id] = {
            "anchors_present": anchor_path.exists(),
            "power_present": power_path.exists(),
            "finding_count": finding_count,
            "review_count": review_count,
        }
    return status


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract Bill X-Ray government power / authority mechanics")
    parser.add_argument("bill_id", nargs="?", help="bill id, e.g. aca or obbba")
    parser.add_argument("--status", action="store_true", help="show power-extractor readiness")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.status:
        print(json.dumps(power_status(), indent=2))
        return 0
    if args.bill_id:
        result = extract_bill(args.bill_id)
        print(f"Extracted {result.finding_count:,} authority candidates for {result.bill_id}")
        return 0

    result = extract_available()
    print(json.dumps(result, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

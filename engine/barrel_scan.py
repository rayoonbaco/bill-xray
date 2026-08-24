"""Pass 8: evidence-bound Barrel Scan candidate detector for Bill X-Ray.

This module does not decide that a provision is improper, wasteful, corrupt, or even
unrelated to a bill. It creates a reproducible review queue from verified Pass 4
section anchors using transparent signals requested by the product doctrine:

topical distance, beneficiary concentration, fiscal significance, scope surprise,
cross-reference opacity, and narrow carve-outs/exemptions.

A flag means "inspect this provision more closely," never "wrongdoing occurred."
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from engine import citations, fiscal_materiality

ROOT = Path(__file__).resolve().parents[1]
ANCHOR_DIR = ROOT / "data" / "citation_anchors"
BARREL_DIR = ROOT / "data" / "barrel_scan"
PROVING_GROUND_BILLS = ("aca", "obbba")
DETECTOR_VERSION = "31.0-canonical-fiscal-signal"

LABEL_POTENTIAL_RIDER = "Potential Rider"
LABEL_SCOPE_SURPRISE = "Scope Surprise"
LABEL_NARROW_CARVEOUT = "Narrow Carve-Out"
LABEL_SPECIFIC_BENEFICIARY = "Highly Specific Beneficiary"
LABEL_CROSSREF_OPACITY = "Cross-Reference Opacity"

_STOPWORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on",
    "or", "the", "to", "with", "without", "under", "this", "that", "act", "section",
    "title", "subtitle", "part", "division", "general", "provisions", "provision",
    "amendment", "amendments", "miscellaneous", "other", "related", "program",
}
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")
_SECTION_HEADING_RE = re.compile(r"^SEC(?:TION)?\.\s*[^.]+\.\s*(.*)$", re.I)
_DOLLAR_RE = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(trillion|billion|million|thousand)?", re.I)
_CROSSREF_RE = re.compile(
    r"\b(?:section|sections|subsection|subsections|paragraph|paragraphs|clause|clauses|title|titles)\s+"
    r"(?:\d+[A-Za-z0-9().-]*|[IVXLC]+)\b|\b\d+\s+U\.S\.C\.\s*§?\s*\d+\b|\bof the Internal Revenue Code\b",
    re.I,
)
_CARVEOUT_RE = re.compile(
    r"\b(?:shall not apply|does not apply|except that|except for|exempt(?:ion|ed)?|waive(?:r|d)?|"
    r"notwithstanding|only if|only for|limited to|other than|special rule for)\b",
    re.I,
)
_SPECIFIC_BENEFICIARY_PATTERNS = (
    re.compile(r"\b(?:project|facility|entity|organization|corporation|institution)\s+(?:known as|named|located (?:in|at))\b", re.I),
    re.compile(r"\b(?:county|parish|borough|municipality|township|city)\s+of\s+[A-Z][A-Za-z .'-]{2,60}\b"),
    re.compile(r"\b(?:located in|located at)\s+[A-Z][A-Za-z .'-]{2,60}(?:,|\.|;)"),
    re.compile(r"\bfor the sole benefit of\b|\bfor the exclusive benefit of\b|\bonly the following (?:entity|entities|project|projects)\b", re.I),
)


@dataclass(frozen=True)
class FactorScores:
    topical_distance: float
    beneficiary_concentration: float
    fiscal_significance: float
    scope_surprise: float
    cross_reference_opacity: float
    narrow_carve_out: float


@dataclass(frozen=True)
class BarrelCandidate:
    schema_version: str
    detector_version: str
    bill_id: str
    anchor_id: str
    segment_id: str
    section_label: str
    status: str
    claim_class: str
    confidence: float
    candidate_score: float
    labels: list[str]
    factors: FactorScores
    why_flagged: list[str]
    operative_excerpt: str
    location_marker: str
    document_ref: str
    source_url: str
    source_sha256: str
    text_sha256: str


@dataclass(frozen=True)
class BarrelIndex:
    schema_version: str
    bill_id: str
    detector_version: str
    source_sha256: str
    candidate_count: int
    high_review_count: int
    dominant_topic_terms: list[str]
    candidates: list[BarrelCandidate]


def _compact(text: str) -> str:
    return " ".join(text.split())


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]


def _heading(text: str) -> str:
    lines = _lines(text)
    if not lines:
        return ""
    match = _SECTION_HEADING_RE.match(lines[0])
    return _compact(match.group(1) if match else lines[0])


def _body(text: str) -> str:
    lines = _lines(text)
    if lines and _SECTION_HEADING_RE.match(lines[0]):
        lines = lines[1:]
    return _compact(" ".join(lines))


def _tokens(text: str) -> set[str]:
    return {
        match.group(0).lower()
        for match in _WORD_RE.finditer(text)
        if match.group(0).lower() not in _STOPWORDS
    }


def build_topic_profile(anchors: list[dict], limit: int = 14) -> list[str]:
    """Build a modest lexical bill-purpose proxy from repeated section-heading terms.

    It is deliberately a proxy, not a semantic claim about the bill's true purpose.
    Later expert/referee passes may override or reject the signal.
    """
    counts: Counter[str] = Counter()
    for anchor in anchors:
        for token in _tokens(_heading(str(anchor.get("exact_text", "")))):
            counts[token] += 1
    repeated = [token for token, count in counts.most_common() if count >= 2]
    if repeated:
        return repeated[:limit]
    return [token for token, _ in counts.most_common(limit)]


def _topical_distance(section_heading: str, topic_terms: list[str]) -> float:
    heading_tokens = _tokens(section_heading)
    profile = set(topic_terms)
    if not heading_tokens or not profile:
        return 0.0
    overlap = len(heading_tokens & profile) / max(1, len(heading_tokens))
    return round(max(0.0, min(1.0, 1.0 - overlap)), 3)


def _beneficiary_concentration(text: str) -> float:
    hits = sum(bool(pattern.search(text)) for pattern in _SPECIFIC_BENEFICIARY_PATTERNS)
    if hits >= 2:
        return 1.0
    if hits == 1:
        return 0.78
    # "only" plus a singular eligible recipient class is a weaker concentration signal.
    if re.search(r"\bonly\b[^.;]{0,100}\b(?:entity|recipient|facility|project|institution)\b", text, re.I):
        return 0.52
    return 0.0


def _largest_dollar_amount(text: str) -> float:
    multipliers = {"": 1.0, "thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
    largest = 0.0
    for match in _DOLLAR_RE.finditer(text):
        number = float(match.group(1).replace(",", ""))
        scale = (match.group(2) or "").lower()
        largest = max(largest, number * multipliers[scale])
    return largest


def _fiscal_significance(text: str) -> float:
    amount = _largest_dollar_amount(text)
    if amount <= 0:
        return 0.0
    # Transparent prototype scale: $1m=.25, $10m=.375, $100m=.5, $1b=.625,
    # $10b=.75, $100b=.875, $1t=1.0. This is a review signal, not a budget score.
    score = (math.log10(max(amount, 1.0)) - 4.0) / 8.0
    return round(max(0.0, min(1.0, score)), 3)


def _crossref_opacity(text: str) -> float:
    hits = len(_CROSSREF_RE.findall(text))
    if hits == 0:
        return 0.0
    external = bool(re.search(r"\b\d+\s+U\.S\.C\.|Internal Revenue Code", text, re.I))
    score = min(1.0, 0.28 + 0.16 * hits + (0.18 if external else 0.0))
    return round(score, 3)


def _carveout_score(text: str) -> float:
    hits = len(_CARVEOUT_RE.findall(text))
    if hits == 0:
        return 0.0
    return round(min(1.0, 0.5 + 0.18 * (hits - 1)), 3)


def _scope_surprise(topical_distance: float, heading: str, text: str) -> float:
    # Scope surprise needs topical distance plus an independent signal. Topical distance
    # alone is too weak to flag a section in a large omnibus bill.
    independent = max(_beneficiary_concentration(text), _carveout_score(text), _crossref_opacity(text), _fiscal_significance(text))
    if topical_distance < 0.55 or independent < 0.35:
        return 0.0
    heading_specificity = min(1.0, len(_tokens(heading)) / 5.0)
    return round(min(1.0, 0.55 * topical_distance + 0.25 * independent + 0.20 * heading_specificity), 3)


def _weighted_score(factors: FactorScores) -> float:
    score = (
        0.20 * factors.topical_distance
        + 0.18 * factors.beneficiary_concentration
        + 0.18 * factors.fiscal_significance
        + 0.18 * factors.scope_surprise
        + 0.14 * factors.cross_reference_opacity
        + 0.12 * factors.narrow_carve_out
    )
    return round(min(1.0, score), 3)


def _labels(f: FactorScores, score: float) -> list[str]:
    labels: list[str] = []
    if f.scope_surprise >= 0.58:
        labels.append(LABEL_SCOPE_SURPRISE)
    if f.narrow_carve_out >= 0.5:
        labels.append(LABEL_NARROW_CARVEOUT)
    if f.beneficiary_concentration >= 0.72:
        labels.append(LABEL_SPECIFIC_BENEFICIARY)
    if f.cross_reference_opacity >= 0.58:
        labels.append(LABEL_CROSSREF_OPACITY)
    # "Potential Rider" requires both material topical distance and scope surprise;
    # it is never generated from a lone keyword or dollar amount.
    if f.topical_distance >= 0.68 and f.scope_surprise >= 0.58 and score >= 0.45:
        labels.insert(0, LABEL_POTENTIAL_RIDER)
    return labels


def _why(f: FactorScores, labels: list[str], amount: float) -> list[str]:
    reasons: list[str] = []
    if f.topical_distance >= 0.55:
        reasons.append(f"Section-heading terms are lexically distant from the bill's repeated heading terms (signal {f.topical_distance:.2f}).")
    if f.beneficiary_concentration >= 0.5:
        reasons.append("Text contains language that may concentrate eligibility or benefit on a specifically described recipient or location.")
    if f.fiscal_significance > 0:
        reasons.append(f"Text contains an explicit dollar amount up to ${amount:,.0f}; fiscal significance is a screening signal, not a judgment of merit.")
    if f.narrow_carve_out >= 0.5:
        reasons.append("Text contains exception, exemption, waiver, limitation, or special-rule language that may narrow who is covered.")
    if f.cross_reference_opacity >= 0.44:
        reasons.append("Understanding the provision requires following one or more statutory cross-references.")
    if LABEL_SCOPE_SURPRISE in labels:
        reasons.append("Topical distance combines with an independent specificity, fiscal, carve-out, or cross-reference signal, so the section deserves scope review.")
    return reasons


def _excerpt(text: str, limit: int = 760) -> str:
    compact = _compact(text)
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


def evaluate_anchor(anchor: dict, topic_terms: list[str], money_finding: dict | None = None) -> BarrelCandidate | None:
    required = (
        "anchor_id", "bill_id", "segment_id", "section_label", "location_marker",
        "document_ref", "source_url", "source_sha256", "text_sha256", "exact_text",
    )
    missing = [key for key in required if key not in anchor]
    if missing:
        raise ValueError(f"Verified anchor is missing required fields: {', '.join(missing)}")
    if not anchor.get("verified"):
        raise ValueError("Barrel Scan requires a verified Pass 4 anchor")

    exact_text = str(anchor["exact_text"])
    heading = _heading(exact_text)
    text = _body(exact_text)
    if not text:
        return None

    topical = _topical_distance(heading, topic_terms)
    beneficiary = _beneficiary_concentration(text)
    # Pass 31: fiscal significance comes from the canonical amount-level money object
    # when available. Contextual/projected figures therefore cannot inflate scrutiny.
    if money_finding is not None:
        fiscal_assessment = fiscal_materiality.assess(money_finding)
        fiscal = fiscal_assessment.score if fiscal_assessment.actionable else 0.0
        actionable_amount = fiscal_assessment.amount if fiscal_assessment.actionable else 0.0
    else:
        # Backward-compatible standalone evaluation for unit tests / pre-money callers.
        fiscal = _fiscal_significance(text)
        actionable_amount = _largest_dollar_amount(text)
    crossref = _crossref_opacity(text)
    carveout = _carveout_score(text)
    surprise = _scope_surprise(topical, heading, text)
    factors = FactorScores(
        topical_distance=topical,
        beneficiary_concentration=beneficiary,
        fiscal_significance=fiscal,
        scope_surprise=surprise,
        cross_reference_opacity=crossref,
        narrow_carve_out=carveout,
    )
    score = _weighted_score(factors)
    labels = _labels(factors, score)

    # Require either a recognized scrutiny label or a multi-signal score. A large
    # dollar amount by itself does not make a Barrel Scan candidate.
    active_signals = sum(value >= 0.5 for value in asdict(factors).values())
    if not labels and not (score >= 0.38 and active_signals >= 2):
        return None

    reasons = _why(factors, labels, actionable_amount)
    if not reasons:
        return None

    confidence = 0.92 if len(labels) >= 2 else 0.84
    return BarrelCandidate(
        schema_version="8.0",
        detector_version=DETECTOR_VERSION,
        bill_id=str(anchor["bill_id"]),
        anchor_id=str(anchor["anchor_id"]),
        segment_id=str(anchor["segment_id"]),
        section_label=str(anchor["section_label"]),
        status="review_candidate",
        claim_class="TEXT",
        confidence=confidence,
        candidate_score=score,
        labels=labels,
        factors=factors,
        why_flagged=reasons,
        operative_excerpt=_excerpt(text),
        location_marker=str(anchor["location_marker"]),
        document_ref=str(anchor["document_ref"]),
        source_url=str(anchor["source_url"]),
        source_sha256=str(anchor["source_sha256"]),
        text_sha256=str(anchor["text_sha256"]),
    )


def _load_verified_section_anchors(bill_id: str) -> tuple[list[dict], str]:
    index_path = ANCHOR_DIR / f"{bill_id}.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Citation anchors not found: {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    anchors: list[dict] = []
    for anchor in index.get("anchors", []):
        if anchor.get("kind") != "section":
            continue
        anchors.append(citations.resolve_anchor(bill_id, str(anchor["anchor_id"])))
    return anchors, str(index.get("source_sha256", ""))


def scan_bill(bill_id: str, *, write: bool = True) -> BarrelIndex:
    anchors, source_sha = _load_verified_section_anchors(bill_id)
    topic_terms = build_topic_profile(anchors)
    money_by_anchor: dict[str, dict] = {}
    money_path = ROOT / "data" / "money" / f"{bill_id}.json"
    if money_path.exists():
        payload = json.loads(money_path.read_text(encoding="utf-8"))
        money_by_anchor = {str(x.get("anchor_id")): x for x in payload.get("findings", []) if x.get("anchor_id")}
    candidates = [candidate for anchor in anchors if (candidate := evaluate_anchor(anchor, topic_terms, money_by_anchor.get(str(anchor.get("anchor_id"))))) is not None]
    candidates.sort(key=lambda item: (-item.candidate_score, item.section_label, item.anchor_id))

    result = BarrelIndex(
        schema_version="8.0",
        bill_id=bill_id,
        detector_version=DETECTOR_VERSION,
        source_sha256=source_sha,
        candidate_count=len(candidates),
        high_review_count=sum(item.candidate_score >= 0.60 for item in candidates),
        dominant_topic_terms=topic_terms,
        candidates=candidates,
    )
    if write:
        BARREL_DIR.mkdir(parents=True, exist_ok=True)
        (BARREL_DIR / f"{bill_id}.json").write_text(
            json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return result


def scan_available(*, write: bool = True) -> dict[str, list[str]]:
    scanned: list[str] = []
    missing_anchors: list[str] = []
    failed: list[str] = []
    for bill_id in PROVING_GROUND_BILLS:
        if not (ANCHOR_DIR / f"{bill_id}.json").exists():
            missing_anchors.append(bill_id)
            continue
        try:
            scan_bill(bill_id, write=write)
            scanned.append(bill_id)
        except (KeyError, ValueError, OSError, json.JSONDecodeError):
            failed.append(bill_id)
    return {"scanned": scanned, "missing_anchors": missing_anchors, "failed": failed}


def barrel_status() -> dict[str, dict]:
    status: dict[str, dict] = {}
    for bill_id in PROVING_GROUND_BILLS:
        anchor_path = ANCHOR_DIR / f"{bill_id}.json"
        barrel_path = BARREL_DIR / f"{bill_id}.json"
        candidate_count = high_review_count = 0
        source_fingerprint_matches = False
        if barrel_path.exists():
            try:
                payload = json.loads(barrel_path.read_text(encoding="utf-8"))
                candidate_count = int(payload.get("candidate_count", 0))
                high_review_count = int(payload.get("high_review_count", 0))
                if anchor_path.exists():
                    anchors = json.loads(anchor_path.read_text(encoding="utf-8"))
                    source_fingerprint_matches = payload.get("source_sha256") == anchors.get("source_sha256")
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        status[bill_id] = {
            "anchors_present": anchor_path.exists(),
            "barrel_artifact_present": barrel_path.exists(),
            "candidate_count": candidate_count,
            "high_review_count": high_review_count,
            "source_fingerprint_matches": source_fingerprint_matches,
        }
    return status


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect evidence-bound Bill X-Ray Barrel Scan review candidates")
    parser.add_argument("bill_id", nargs="?", help="bill id, e.g. aca or obbba")
    parser.add_argument("--status", action="store_true", help="show Barrel Scan readiness")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.status:
        print(json.dumps(barrel_status(), indent=2))
        return 0
    if args.bill_id:
        result = scan_bill(args.bill_id)
        print(f"Detected {result.candidate_count:,} Barrel Scan review candidates for {result.bill_id}")
        return 0

    result = scan_available()
    print(json.dumps(result, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Pass 9: dynamic topic-expert routing and review packets for Bill X-Ray.

The public product stays simple, but legislation is not one-domain-at-a-time. This
module routes each verified statutory section to the specialist domain(s) that are
actually relevant to that section and builds a source-bound review packet from the
evidence layers created in Passes 4-8.

Important boundary: routing is not a substantive conclusion. A topic expert may
identify context that must be checked, but no expert note becomes a public claim
until the later skeptic/referee passes admit it under the Bill X-Ray evidence rule.
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
MONEY_DIR = ROOT / "data" / "money"
POWER_DIR = ROOT / "data" / "power"
BARREL_DIR = ROOT / "data" / "barrel_scan"
TOPIC_DIR = ROOT / "data" / "topic_reviews"
PROVING_GROUND_BILLS = ("aca", "obbba")
REVIEWER_VERSION = "31.6.2.4-lexical-routing"

# Deliberately compact taxonomy. It is broad enough to route the first catalog
# without pretending that one label describes an entire omnibus bill.
DOMAIN_RULES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "health": (
        ("health", "medical", "medicare", "medicaid", "hospital", "insurance", "patient", "provider", "pharmacy", "drug", "coverage", "public health"),
        ("Review eligibility, coverage, benefit design, provider/payment mechanics, and implementation dependencies.",
         "Check whether a technical health term changes who receives care, who pays, or what an agency/provider must do."),
    ),
    "tax": (
        ("tax", "taxpayer", "taxable", "deduction", "credit", "internal revenue", "excise", "basis", "withholding", "gross income", "refund"),
        ("Review tax base, eligibility, phase-ins/phase-outs, timing, refundability, and interactions with existing Code sections.",
         "Separate the statutory tax mechanism from later revenue or distribution estimates."),
    ),
    "finance": (
        ("bank", "banking", "financial", "securities", "exchange", "credit union", "mortgage", "lender", "loan", "capital", "deposit", "consumer finance"),
        ("Review regulated entities, capital/credit mechanics, consumer protections, market structure, and supervisory authority.",
         "Check cross-references to existing financial law before describing the practical effect."),
    ),
    "defense_security": (
        ("defense", "military", "armed forces", "national security", "intelligence", "homeland security", "weapon", "veteran", "classified", "terrorism"),
        ("Review mission authority, procurement, readiness, intelligence/security scope, and civil-military or domestic implications.",
         "Distinguish authorization, appropriation, and operational discretion."),
    ),
    "energy": (
        ("energy", "electric", "electricity", "grid", "power plant", "utility", "nuclear", "solar", "wind", "oil", "gas", "fuel", "pipeline"),
        ("Review generation, transmission, reliability, permitting, incentives, fuel markets, and ratepayer implications.",
         "Separate statutory incentives from modeled energy-market outcomes."),
    ),
    "environment": (
        ("environment", "environmental", "emission", "pollution", "climate", "air quality", "water quality", "hazardous", "conservation", "wildlife", "clean air", "clean water"),
        ("Review permitting, standards, compliance duties, environmental baselines, exemptions, and federal/state implementation.",
         "Check whether referenced environmental statutes carry definitions or procedures not repeated here."),
    ),
    "agriculture": (
        ("agriculture", "agricultural", "farm", "farmer", "crop", "livestock", "commodity", "rural", "nutrition assistance", "snap", "forestry"),
        ("Review producer eligibility, commodity/support mechanics, conservation conditions, rural effects, and nutrition-program interactions.",
         "Check whether benefits or restrictions turn on acreage, production, income, or geographic definitions."),
    ),
    "technology": (
        ("technology", "semiconductor", "chip", "cyber", "cybersecurity", "artificial intelligence", "software", "data", "broadband", "telecommunications", "spectrum", "digital"),
        ("Review technical scope, standards, cybersecurity/data duties, procurement, competition, and implementation feasibility.",
         "Do not translate a technology authorization into a capability claim without technical evidence."),
    ),
    "labor": (
        ("labor", "worker", "employee", "employer", "employment", "wage", "workforce", "unemployment", "collective bargaining", "occupational"),
        ("Review worker/employer coverage, eligibility, enforcement, labor-market incentives, and interaction with existing labor law.",
         "Separate statutory duties from predictions about jobs or wages."),
    ),
    "infrastructure_transport": (
        ("infrastructure", "highway", "road", "bridge", "transit", "rail", "airport", "port", "transportation", "water system", "construction"),
        ("Review project eligibility, funding channels, permitting, matching requirements, asset ownership, and implementation timelines.",
         "Check whether a named project or geography is a general program criterion or a narrow beneficiary."),
    ),
    "education": (
        ("education", "school", "student", "college", "university", "teacher", "scholarship", "student loan", "higher education"),
        ("Review institutional/student eligibility, funding conditions, rights/obligations, and federal/state/local education roles.",
         "Separate statutory aid mechanics from claims about educational outcomes."),
    ),
    "housing": (
        ("housing", "tenant", "landlord", "rental", "rent", "homeless", "public housing", "affordable housing", "homeowner", "foreclosure"),
        ("Review household/property eligibility, subsidy or credit mechanics, lender/landlord duties, and federal/local implementation.",
         "Check whether affordability or supply effects require evidence beyond the statutory text."),
    ),
    "immigration": (
        ("immigration", "immigrant", "alien", "visa", "citizenship", "naturalization", "border", "asylum", "refugee", "deport", "removal proceedings"),
        ("Review status categories, eligibility, procedural rights, enforcement authority, and interactions with existing immigration law.",
         "Avoid inferring population-level effects from a status or procedure change without outside evidence."),
    ),
    "civil_liberties_justice": (
        ("privacy", "surveillance", "search", "warrant", "criminal", "crime", "court", "judicial", "detention", "due process", "civil rights", "discrimination", "first amendment"),
        ("Review rights, procedures, standards, remedies, enforcement, judicial review, and government access to people/data/property.",
         "Flag constitutional implications as legal questions unless adjudicated authority establishes them."),
    ),
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")


@dataclass(frozen=True)
class DomainScore:
    domain: str
    score: float
    matched_terms: list[str]


@dataclass(frozen=True)
class TopicReview:
    schema_version: str
    reviewer_version: str
    bill_id: str
    anchor_id: str
    segment_id: str
    section_label: str
    status: str
    claim_class: str
    routing_confidence: float
    primary_domain: str
    expert_domains: list[str]
    domain_scores: list[DomainScore]
    review_questions: list[str]
    evidence_layers_present: list[str]
    evidence_snapshot: dict
    context_needed: list[str]
    location_marker: str
    document_ref: str
    source_url: str
    source_sha256: str
    text_sha256: str


@dataclass(frozen=True)
class TopicReviewIndex:
    schema_version: str
    bill_id: str
    reviewer_version: str
    source_sha256: str
    review_count: int
    multi_expert_count: int
    human_assignment_count: int
    reviews: list[TopicReview]


def _compact(text: str) -> str:
    return " ".join(str(text).split())


def _body(exact_text: str) -> str:
    lines = [line.strip() for line in str(exact_text).replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [line for line in lines if line]
    return _compact(" ".join(lines))


def _term_occurrences(haystack: str, term: str) -> int:
    """Count lexical term matches without substring collisions (e.g. port/research/current)."""
    pattern = r"(?<![A-Za-z0-9])" + re.escape(term.lower()) + r"(?![A-Za-z0-9])"
    return len(re.findall(pattern, haystack, flags=re.IGNORECASE))


def score_domains(text: str) -> list[DomainScore]:
    haystack = _body(text).lower()
    scores: list[DomainScore] = []
    for domain, (terms, _questions) in DOMAIN_RULES.items():
        matched: list[str] = []
        raw = 0.0
        for term in terms:
            term_l = term.lower()
            occurrences = _term_occurrences(haystack, term_l)
            if occurrences:
                matched.append(term)
                # Phrase/specific-term hits count more than a single broad word.
                raw += min(2.5, 1.0 + 0.35 * (occurrences - 1) + (0.45 if " " in term_l else 0.0))
        if matched:
            scores.append(DomainScore(domain=domain, score=round(raw, 3), matched_terms=matched[:10]))
    return sorted(scores, key=lambda item: (-item.score, item.domain))


def route_domains(text: str, *, max_experts: int = 3) -> tuple[list[DomainScore], list[str], float, bool]:
    scores = score_domains(text)
    if not scores:
        return [], ["general_legislative"], 0.45, True

    top = scores[0].score
    selected = [item.domain for item in scores if item.score >= max(1.0, top * 0.48)][:max_experts]
    if not selected:
        selected = [scores[0].domain]

    second = scores[1].score if len(scores) > 1 else 0.0
    separation = max(0.0, top - second)
    confidence = min(0.98, 0.72 + min(top, 5.0) * 0.04 + min(separation, 3.0) * 0.025)
    if len(selected) > 1:
        confidence = max(confidence, 0.84)
    return scores, selected, round(confidence, 3), False


def _index_by_anchor(directory: Path, bill_id: str, collection_key: str) -> dict[str, dict]:
    path = directory / f"{bill_id}.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get(collection_key, [])
    return {str(item.get("anchor_id")): item for item in items if item.get("anchor_id")}


def _barrel_index(bill_id: str) -> dict[str, dict]:
    path = BARREL_DIR / f"{bill_id}.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(item.get("anchor_id")): item for item in payload.get("candidates", []) if item.get("anchor_id")}


def _review_questions(domains: Iterable[str]) -> list[str]:
    questions: list[str] = []
    for domain in domains:
        if domain == "general_legislative":
            candidates = (
                "Identify the substantive policy domain before making an effect claim.",
                "Resolve definitions and cross-references that materially change the section's operation.",
            )
        else:
            candidates = DOMAIN_RULES[domain][1]
        for question in candidates:
            if question not in questions:
                questions.append(question)
    return questions[:6]


def build_review(
    anchor: dict,
    *,
    money_finding: dict | None = None,
    power_finding: dict | None = None,
    barrel_candidate: dict | None = None,
) -> TopicReview:
    required = (
        "anchor_id", "bill_id", "segment_id", "section_label", "location_marker",
        "document_ref", "source_url", "source_sha256", "text_sha256", "exact_text",
    )
    missing = [key for key in required if key not in anchor]
    if missing:
        raise ValueError(f"Verified anchor is missing required fields: {', '.join(missing)}")
    if not anchor.get("verified"):
        raise ValueError("Topic-expert review requires a verified Pass 4 anchor")

    scores, domains, confidence, needs_human = route_domains(str(anchor["exact_text"]))
    layers = ["citation_anchor"]
    snapshot: dict[str, object] = {}
    context_needed: list[str] = []

    if money_finding:
        layers.append("money")
        snapshot["money"] = {
            "money_types": money_finding.get("money_types", []),
            "amounts": money_finding.get("amounts", []),
            "status": money_finding.get("status"),
        }
        if money_finding.get("status") == "needs_fiscal_context":
            context_needed.append("Authoritative fiscal context is needed before stating budget or distribution effects.")
    if power_finding:
        layers.append("power")
        snapshot["power"] = {
            "authority_types": power_finding.get("authority_types", []),
            "actors": power_finding.get("actors", []),
            "authority_direction": power_finding.get("authority_direction"),
            "status": power_finding.get("status"),
        }
        if power_finding.get("status") == "needs_legal_context":
            context_needed.append("Legal/cross-reference context is needed before stating the full scope of authority.")
    if barrel_candidate:
        layers.append("barrel_scan")
        snapshot["barrel_scan"] = {
            "labels": barrel_candidate.get("labels", []),
            "why_flagged": barrel_candidate.get("why_flagged", []),
            "status": barrel_candidate.get("status"),
        }
        context_needed.append("Barrel Scan is a scrutiny flag only; expert review must not convert it into a wrongdoing claim.")

    if needs_human:
        context_needed.insert(0, "No specialist domain was strong enough for automatic assignment; assign a human/topic specialist before effect analysis.")

    return TopicReview(
        schema_version="9.0",
        reviewer_version=REVIEWER_VERSION,
        bill_id=str(anchor["bill_id"]),
        anchor_id=str(anchor["anchor_id"]),
        segment_id=str(anchor["segment_id"]),
        section_label=str(anchor["section_label"]),
        status="needs_human_topic_assignment" if needs_human else "expert_review_packet_ready",
        claim_class="UNKNOWN",  # The routing packet itself is not a public effect claim.
        routing_confidence=confidence,
        primary_domain=domains[0],
        expert_domains=domains,
        domain_scores=scores[:8],
        review_questions=_review_questions(domains),
        evidence_layers_present=layers,
        evidence_snapshot=snapshot,
        context_needed=context_needed,
        location_marker=str(anchor["location_marker"]),
        document_ref=str(anchor["document_ref"]),
        source_url=str(anchor["source_url"]),
        source_sha256=str(anchor["source_sha256"]),
        text_sha256=str(anchor["text_sha256"]),
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
        item = citations.resolve_anchor(bill_id, str(anchor["anchor_id"]))
        if not item.get("verified"):
            raise ValueError(f"Anchor failed verification: {anchor['anchor_id']}")
        resolved.append(item)
    return resolved


def review_bill(bill_id: str) -> TopicReviewIndex:
    anchors = _load_verified_section_anchors(bill_id)
    if not anchors:
        raise ValueError(f"No verified section anchors available for {bill_id}")

    money = _index_by_anchor(MONEY_DIR, bill_id, "findings")
    power = _index_by_anchor(POWER_DIR, bill_id, "findings")
    barrel = _barrel_index(bill_id)

    reviews = [
        build_review(
            anchor,
            money_finding=money.get(str(anchor["anchor_id"])),
            power_finding=power.get(str(anchor["anchor_id"])),
            barrel_candidate=barrel.get(str(anchor["anchor_id"])),
        )
        for anchor in anchors
    ]
    result = TopicReviewIndex(
        schema_version="9.0",
        bill_id=bill_id,
        reviewer_version=REVIEWER_VERSION,
        source_sha256=str(anchors[0]["source_sha256"]),
        review_count=len(reviews),
        multi_expert_count=sum(1 for item in reviews if len(item.expert_domains) > 1),
        human_assignment_count=sum(1 for item in reviews if item.status == "needs_human_topic_assignment"),
        reviews=reviews,
    )
    TOPIC_DIR.mkdir(parents=True, exist_ok=True)
    (TOPIC_DIR / f"{bill_id}.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result


def topic_status() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for bill_id in PROVING_GROUND_BILLS:
        anchor_path = ANCHOR_DIR / f"{bill_id}.json"
        review_path = TOPIC_DIR / f"{bill_id}.json"
        state: dict[str, object] = {
            "citation_anchors_ready": anchor_path.exists(),
            "topic_review_ready": review_path.exists(),
            "review_count": 0,
            "multi_expert_count": 0,
            "human_assignment_count": 0,
            "reviewer_version": REVIEWER_VERSION,
        }
        if review_path.exists():
            payload = json.loads(review_path.read_text(encoding="utf-8"))
            state["review_count"] = int(payload.get("review_count", 0))
            state["multi_expert_count"] = int(payload.get("multi_expert_count", 0))
            state["human_assignment_count"] = int(payload.get("human_assignment_count", 0))
        result[bill_id] = state
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Pass 9 dynamic topic-expert review packets.")
    parser.add_argument("bill_ids", nargs="*", default=list(PROVING_GROUND_BILLS))
    args = parser.parse_args(argv)
    failed = False
    for bill_id in args.bill_ids:
        try:
            result = review_bill(bill_id)
            print(
                f"{bill_id}: {result.review_count} review packets, "
                f"{result.multi_expert_count} multi-expert, "
                f"{result.human_assignment_count} need human topic assignment"
            )
        except Exception as exc:
            failed = True
            print(f"{bill_id}: ERROR - {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

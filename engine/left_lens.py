"""Pass 10: source-bound progressive advocacy review for Bill X-Ray.

The Left Lens is advocacy, not statutory fact. It builds the strongest good-faith
progressive interpretation *candidate* for each verified statutory section from the
evidence layers created in Passes 4-9. Every candidate stays explicitly classified
as INTERPRETATION and retains the exact citation anchor that bounds the argument.

This pass does not publish the final LEFT column. The later Right Lens, skeptic,
neutral referee, and five-panel synthesis decide which interpretations survive.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from engine import citations

ROOT = Path(__file__).resolve().parents[1]
ANCHOR_DIR = ROOT / "data" / "citation_anchors"
MONEY_DIR = ROOT / "data" / "money"
POWER_DIR = ROOT / "data" / "power"
BARREL_DIR = ROOT / "data" / "barrel_scan"
TOPIC_DIR = ROOT / "data" / "topic_reviews"
LEFT_DIR = ROOT / "data" / "left_lens"
PROVING_GROUND_BILLS = ("aca", "obbba")
REVIEWER_VERSION = "10.0-good-faith-progressive"

# These are questions/frames, not conclusions. They help the advocate steel-man a
# progressive reading without pre-judging whether the provision is good or bad.
DOMAIN_FRAMES: dict[str, tuple[str, ...]] = {
    "health": (
        "Does the provision expand affordable access, continuity of coverage, public health capacity, or patient protection?",
        "Could implementation burdens, exclusions, or provider incentives undermine equitable access?",
    ),
    "tax": (
        "Who receives the tax benefit or bears the tax burden, and is the distribution progressive or regressive?",
        "Does the mechanism strengthen broad household security or concentrate benefits among higher-income or corporate actors?",
    ),
    "finance": (
        "Does the provision strengthen consumer protection, systemic stability, accountability, or fair access to credit?",
        "Could deregulation, concentration, or weak enforcement shift risk onto households or the public?",
    ),
    "defense_security": (
        "Does the provision protect legitimate security needs while preserving democratic oversight and civil liberties?",
        "Are costs, emergency powers, procurement choices, or domestic spillovers sufficiently constrained and accountable?",
    ),
    "energy": (
        "Does the provision accelerate reliable clean energy, affordability, resilience, or broadly shared infrastructure benefits?",
        "Could costs, pollution, siting burdens, or market benefits fall unevenly on lower-income communities?",
    ),
    "environment": (
        "Does the provision protect public health, environmental quality, climate resilience, or frontline communities?",
        "Do exemptions or implementation choices weaken safeguards or shift environmental burdens onto less powerful groups?",
    ),
    "agriculture": (
        "Does the provision support family farms, rural resilience, nutrition access, conservation, or fair market participation?",
        "Could benefits concentrate among large producers or leave vulnerable households and smaller operators behind?",
    ),
    "technology": (
        "Does the provision broaden access to innovation while protecting workers, consumers, privacy, competition, and public accountability?",
        "Could public support privatize gains while socializing risk, surveillance, displacement, or market concentration?",
    ),
    "labor": (
        "Does the provision strengthen worker bargaining power, wages, safety, benefits, job quality, or access to employment?",
        "Could flexibility or employer discretion weaken worker protections or shift risk onto employees?",
    ),
    "infrastructure_transport": (
        "Does the provision expand reliable public infrastructure, access, jobs, safety, or community resilience?",
        "Are funding, siting, displacement, environmental, and local-benefit effects distributed fairly?",
    ),
    "education": (
        "Does the provision widen educational access, affordability, quality, or opportunity across income and geography?",
        "Could eligibility rules, financing choices, or institutional incentives deepen existing inequities?",
    ),
    "housing": (
        "Does the provision improve housing affordability, stability, supply, tenant protection, or access to homeownership?",
        "Could subsidies, financing, or regulatory choices disproportionately benefit owners, investors, or higher-income households?",
    ),
    "immigration": (
        "Does the provision preserve due process, family unity, humane treatment, orderly pathways, and workable administration?",
        "Could enforcement or eligibility rules create disproportionate burdens or weaken procedural protections?",
    ),
    "civil_liberties_justice": (
        "Does the provision protect due process, equal treatment, privacy, voting/civil rights, and accountable enforcement?",
        "Could new powers, penalties, surveillance, or procedural limits fall unevenly on marginalized communities?",
    ),
    "general_legislative": (
        "What distributional, rights, public-capacity, labor, environmental, or democratic-accountability question would a progressive advocate consider most important?",
        "What factual context is still missing before a responsible progressive interpretation can be stated?",
    ),
}


@dataclass(frozen=True)
class LeftLensCandidate:
    schema_version: str
    reviewer_version: str
    bill_id: str
    anchor_id: str
    segment_id: str
    section_label: str
    lens: str
    claim_class: str
    status: str
    confidence: float
    expert_domains: list[str]
    progressive_questions: list[str]
    evidence_layers_present: list[str]
    evidence_snapshot: dict
    strongest_case_instruction: str
    counterweight_instruction: str
    external_evidence_needed: list[str]
    forbidden_moves: list[str]
    location_marker: str
    document_ref: str
    source_url: str
    source_sha256: str
    text_sha256: str


@dataclass(frozen=True)
class LeftLensIndex:
    schema_version: str
    bill_id: str
    reviewer_version: str
    source_sha256: str
    candidate_count: int
    ready_count: int
    context_needed_count: int
    candidates: list[LeftLensCandidate]


def _load_index(directory: Path, bill_id: str, key: str) -> dict[str, dict]:
    path = directory / f"{bill_id}.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(item["anchor_id"]): item
        for item in payload.get(key, [])
        if item.get("anchor_id")
    }


def _load_barrel(bill_id: str) -> dict[str, dict]:
    return _load_index(BARREL_DIR, bill_id, "candidates")


def _questions(domains: list[str]) -> list[str]:
    questions: list[str] = []
    for domain in domains or ["general_legislative"]:
        for question in DOMAIN_FRAMES.get(domain, DOMAIN_FRAMES["general_legislative"]):
            if question not in questions:
                questions.append(question)
    return questions[:6]


def build_candidate(
    anchor: dict,
    *,
    money_finding: dict | None = None,
    power_finding: dict | None = None,
    barrel_candidate: dict | None = None,
    topic_review: dict | None = None,
) -> LeftLensCandidate:
    required = (
        "anchor_id", "bill_id", "segment_id", "section_label", "location_marker",
        "document_ref", "source_url", "source_sha256", "text_sha256", "exact_text",
    )
    missing = [key for key in required if key not in anchor]
    if missing:
        raise ValueError(f"Verified anchor is missing required fields: {', '.join(missing)}")
    if not anchor.get("verified"):
        raise ValueError("Left Lens requires a verified Pass 4 anchor")

    layers = ["citation_anchor"]
    snapshot: dict[str, object] = {
        "text_excerpt": " ".join(str(anchor["exact_text"]).split())[:900],
    }
    external_needed: list[str] = []

    if money_finding:
        layers.append("money")
        snapshot["money"] = {
            "categories": money_finding.get("categories", money_finding.get("money_types", [])),
            "amounts": money_finding.get("amounts", []),
            "percentages": money_finding.get("percentages", []),
            "fiscal_direction": money_finding.get("fiscal_direction"),
            "status": money_finding.get("status"),
        }
        external_needed.append("Use authoritative fiscal/distribution evidence before asserting who ultimately gains, pays, or how large the budget effect is.")

    if power_finding:
        layers.append("power")
        snapshot["power"] = {
            "authority_types": power_finding.get("authority_types", []),
            "actors": power_finding.get("actors", []),
            "authority_direction": power_finding.get("authority_direction"),
            "status": power_finding.get("status"),
        }
        if power_finding.get("status") == "needs_legal_context":
            external_needed.append("Resolve legal/cross-reference context before arguing about the practical scope of government power.")

    if barrel_candidate:
        layers.append("barrel_scan")
        snapshot["barrel_scan"] = {
            "labels": barrel_candidate.get("labels", []),
            "why_flagged": barrel_candidate.get("why_flagged", []),
            "status": barrel_candidate.get("status"),
        }
        external_needed.append("A Barrel Scan flag is not evidence of favoritism or wrongdoing; establish motive/beneficiary effects separately if relevant.")

    domains = ["general_legislative"]
    topic_status = None
    if topic_review:
        layers.append("topic_review")
        domains = list(topic_review.get("expert_domains") or [topic_review.get("primary_domain") or "general_legislative"])
        topic_status = topic_review.get("status")
        snapshot["topic_review"] = {
            "primary_domain": topic_review.get("primary_domain"),
            "expert_domains": domains,
            "routing_confidence": topic_review.get("routing_confidence"),
            "status": topic_status,
            "context_needed": topic_review.get("context_needed", []),
        }
        if topic_status == "needs_human_topic_assignment":
            external_needed.append("Assign the correct subject-matter expert before making a substantive progressive interpretation.")

    status = "advocate_packet_ready"
    confidence = 0.86
    if topic_status == "needs_human_topic_assignment":
        status = "needs_context"
        confidence = 0.62
    elif any(
        item and item.get("status") in {"needs_fiscal_context", "needs_legal_context"}
        for item in (money_finding, power_finding)
    ):
        status = "needs_context"
        confidence = 0.72
    elif topic_review:
        confidence = min(0.94, max(0.82, float(topic_review.get("routing_confidence", 0.82))))

    return LeftLensCandidate(
        schema_version="10.0",
        reviewer_version=REVIEWER_VERSION,
        bill_id=str(anchor["bill_id"]),
        anchor_id=str(anchor["anchor_id"]),
        segment_id=str(anchor["segment_id"]),
        section_label=str(anchor["section_label"]),
        lens="LEFT",
        claim_class="INTERPRETATION",
        status=status,
        confidence=round(confidence, 3),
        expert_domains=domains,
        progressive_questions=_questions(domains),
        evidence_layers_present=layers,
        evidence_snapshot=snapshot,
        strongest_case_instruction=(
            "State the strongest good-faith progressive interpretation supported by this evidence packet. "
            "Explain the public-interest value or concern a sophisticated progressive advocate would emphasize."
        ),
        counterweight_instruction=(
            "Identify the strongest fact, tradeoff, implementation risk, or uncertainty that could weaken that progressive interpretation."
        ),
        external_evidence_needed=list(dict.fromkeys(external_needed)),
        forbidden_moves=[
            "Do not present this interpretation as statutory text or direct effect.",
            "Do not infer intent, corruption, bad faith, or hidden motive from the provision alone.",
            "Do not invent beneficiaries, fiscal effects, outcomes, or constitutional conclusions not established by evidence.",
            "Do not weaken the opposing case; later passes must receive a steel-mannable record.",
        ],
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


def build_left_lens(bill_id: str) -> LeftLensIndex:
    anchors = _load_verified_section_anchors(bill_id)
    if not anchors:
        raise ValueError(f"No verified section anchors available for {bill_id}")

    money = _load_index(MONEY_DIR, bill_id, "findings")
    power = _load_index(POWER_DIR, bill_id, "findings")
    barrel = _load_barrel(bill_id)
    topic = _load_index(TOPIC_DIR, bill_id, "reviews")

    candidates = [
        build_candidate(
            anchor,
            money_finding=money.get(str(anchor["anchor_id"])),
            power_finding=power.get(str(anchor["anchor_id"])),
            barrel_candidate=barrel.get(str(anchor["anchor_id"])),
            topic_review=topic.get(str(anchor["anchor_id"])),
        )
        for anchor in anchors
    ]

    result = LeftLensIndex(
        schema_version="10.0",
        bill_id=bill_id,
        reviewer_version=REVIEWER_VERSION,
        source_sha256=str(anchors[0]["source_sha256"]),
        candidate_count=len(candidates),
        ready_count=sum(1 for item in candidates if item.status == "advocate_packet_ready"),
        context_needed_count=sum(1 for item in candidates if item.status == "needs_context"),
        candidates=candidates,
    )
    LEFT_DIR.mkdir(parents=True, exist_ok=True)
    (LEFT_DIR / f"{bill_id}.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result


def left_status() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for bill_id in PROVING_GROUND_BILLS:
        anchor_path = ANCHOR_DIR / f"{bill_id}.json"
        left_path = LEFT_DIR / f"{bill_id}.json"
        state: dict[str, object] = {
            "citation_anchors_ready": anchor_path.exists(),
            "left_lens_ready": left_path.exists(),
            "candidate_count": 0,
            "ready_count": 0,
            "context_needed_count": 0,
            "reviewer_version": REVIEWER_VERSION,
        }
        if left_path.exists():
            payload = json.loads(left_path.read_text(encoding="utf-8"))
            state["candidate_count"] = int(payload.get("candidate_count", 0))
            state["ready_count"] = int(payload.get("ready_count", 0))
            state["context_needed_count"] = int(payload.get("context_needed_count", 0))
        result[bill_id] = state
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Pass 10 progressive advocacy review packets.")
    parser.add_argument("bill_ids", nargs="*", default=list(PROVING_GROUND_BILLS))
    args = parser.parse_args(argv)
    failed = False
    for bill_id in args.bill_ids:
        try:
            result = build_left_lens(bill_id)
            print(
                f"{bill_id}: {result.candidate_count} Left Lens packets, "
                f"{result.ready_count} ready, {result.context_needed_count} need context"
            )
        except Exception as exc:
            failed = True
            print(f"{bill_id}: ERROR - {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

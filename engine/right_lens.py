"""Pass 11: source-bound conservative advocacy review for Bill X-Ray.

The Right Lens is advocacy, not statutory fact. It builds the strongest good-faith
conservative interpretation candidate for each verified statutory section from the
evidence layers created in Passes 4-9. Every candidate stays explicitly classified
as INTERPRETATION and retains the exact citation anchor that bounds the argument.

This pass does not publish the final RIGHT column. The investigative skeptic,
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
RIGHT_DIR = ROOT / "data" / "right_lens"
PROVING_GROUND_BILLS = ("aca", "obbba")
REVIEWER_VERSION = "11.0-good-faith-conservative"

# These are questions/frames, not conclusions. They help the advocate steel-man a
# conservative reading without pre-judging whether the provision is good or bad.
DOMAIN_FRAMES: dict[str, tuple[str, ...]] = {
    "health": (
        "Does the provision preserve patient choice, provider competition, local flexibility, and sustainable public commitments?",
        "Could mandates, subsidies, price controls, or federal administration create dependency, distort incentives, or crowd out private options?",
    ),
    "tax": (
        "Does the provision improve incentives to work, save, invest, form businesses, or keep economic decisions with households and firms?",
        "Does the tax mechanism create complexity, unequal treatment, hidden phaseouts, or a larger long-term burden on taxpayers?",
    ),
    "finance": (
        "Does the provision preserve competitive markets, access to capital, property rights, and clear rules without unnecessary regulatory burden?",
        "Could compliance costs, discretionary regulation, or government backstops create concentration, moral hazard, or reduced credit availability?",
    ),
    "defense_security": (
        "Does the provision strengthen deterrence, readiness, border or homeland security, and clear executive capacity while preserving constitutional limits?",
        "Are spending, surveillance, emergency powers, procurement, and mission scope sufficiently disciplined and accountable?",
    ),
    "energy": (
        "Does the provision improve reliable, affordable, abundant domestic energy while reducing dependence on fragile foreign supply chains?",
        "Could subsidies, mandates, permitting rules, or technology preferences distort markets or shift costs to ratepayers and taxpayers?",
    ),
    "environment": (
        "Does the provision protect air, water, land, and public health while respecting property rights, federalism, and workable compliance costs?",
        "Could federal mandates, permitting delays, or broad administrative discretion impose disproportionate burdens without commensurate environmental gains?",
    ),
    "agriculture": (
        "Does the provision protect farm viability, food security, private property, rural communities, and competitive agricultural markets?",
        "Could subsidies, eligibility rules, or federal controls distort production decisions or disproportionately favor large incumbents?",
    ),
    "technology": (
        "Does the provision support innovation, entrepreneurship, competition, security, and American technological leadership with limited government distortion?",
        "Could public funding, regulation, surveillance authority, or compliance mandates entrench incumbents, weaken privacy, or socialize private risk?",
    ),
    "labor": (
        "Does the provision expand employment, wage growth, worker choice, mobility, entrepreneurship, and flexibility in how people and firms organize work?",
        "Could mandates, benefit rules, or bargaining requirements reduce hiring, raise entry barriers, or limit worker and employer flexibility?",
    ),
    "infrastructure_transport": (
        "Does the provision deliver durable infrastructure, public safety, economic connectivity, and local value with disciplined spending and permitting?",
        "Are projects prioritized by need and measurable benefit, or could federal conditions, delays, or subsidies weaken cost control and local accountability?",
    ),
    "education": (
        "Does the provision increase parental choice, local control, educational pluralism, accountability, and pathways to skills and employment?",
        "Could federal conditions, subsidies, debt structures, or institutional incentives weaken price discipline or displace state, local, or family decision-making?",
    ),
    "housing": (
        "Does the provision expand housing supply, ownership opportunity, local flexibility, and market entry without creating unsustainable taxpayer exposure?",
        "Could subsidies, mandates, or credit interventions inflate prices, weaken underwriting discipline, or displace local land-use authority?",
    ),
    "immigration": (
        "Does the provision support lawful immigration, border security, enforceable rules, national sovereignty, and predictable administration?",
        "Could eligibility, parole, enforcement, or procedural rules weaken deterrence, strain public systems, or reduce democratic control over admission policy?",
    ),
    "civil_liberties_justice": (
        "Does the provision protect constitutional rights, due process, equal treatment, public safety, and limits on government coercion?",
        "Could enforcement, surveillance, penalties, compelled speech, or administrative discretion exceed clear statutory and constitutional boundaries?",
    ),
    "general_legislative": (
        "What question about limited government, individual liberty, federalism, fiscal discipline, public safety, market incentives, or institutional accountability would a conservative advocate consider most important?",
        "What factual context is still missing before a responsible conservative interpretation can be stated?",
    ),
}


@dataclass(frozen=True)
class RightLensCandidate:
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
    conservative_questions: list[str]
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
class RightLensIndex:
    schema_version: str
    bill_id: str
    reviewer_version: str
    source_sha256: str
    candidate_count: int
    ready_count: int
    context_needed_count: int
    candidates: list[RightLensCandidate]


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
) -> RightLensCandidate:
    required = (
        "anchor_id", "bill_id", "segment_id", "section_label", "location_marker",
        "document_ref", "source_url", "source_sha256", "text_sha256", "exact_text",
    )
    missing = [key for key in required if key not in anchor]
    if missing:
        raise ValueError(f"Verified anchor is missing required fields: {', '.join(missing)}")
    if not anchor.get("verified"):
        raise ValueError("Right Lens requires a verified Pass 4 anchor")

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
        external_needed.append(
            "Use authoritative fiscal/distribution evidence before asserting who ultimately gains, pays, or how large the budget effect is."
        )

    if power_finding:
        layers.append("power")
        snapshot["power"] = {
            "authority_types": power_finding.get("authority_types", []),
            "actors": power_finding.get("actors", []),
            "authority_direction": power_finding.get("authority_direction"),
            "status": power_finding.get("status"),
        }
        if power_finding.get("status") == "needs_legal_context":
            external_needed.append(
                "Resolve legal/cross-reference context before arguing about the practical scope of government power."
            )

    if barrel_candidate:
        layers.append("barrel_scan")
        snapshot["barrel_scan"] = {
            "labels": barrel_candidate.get("labels", []),
            "why_flagged": barrel_candidate.get("why_flagged", []),
            "status": barrel_candidate.get("status"),
        }
        external_needed.append(
            "A Barrel Scan flag is not evidence of favoritism or wrongdoing; establish motive/beneficiary effects separately if relevant."
        )

    domains = ["general_legislative"]
    topic_status = None
    if topic_review:
        layers.append("topic_review")
        domains = list(
            topic_review.get("expert_domains")
            or [topic_review.get("primary_domain") or "general_legislative"]
        )
        topic_status = topic_review.get("status")
        snapshot["topic_review"] = {
            "primary_domain": topic_review.get("primary_domain"),
            "expert_domains": domains,
            "routing_confidence": topic_review.get("routing_confidence"),
            "status": topic_status,
            "context_needed": topic_review.get("context_needed", []),
        }
        if topic_status == "needs_human_topic_assignment":
            external_needed.append(
                "Assign the correct subject-matter expert before making a substantive conservative interpretation."
            )

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

    return RightLensCandidate(
        schema_version="11.0",
        reviewer_version=REVIEWER_VERSION,
        bill_id=str(anchor["bill_id"]),
        anchor_id=str(anchor["anchor_id"]),
        segment_id=str(anchor["segment_id"]),
        section_label=str(anchor["section_label"]),
        lens="RIGHT",
        claim_class="INTERPRETATION",
        status=status,
        confidence=round(confidence, 3),
        expert_domains=domains,
        conservative_questions=_questions(domains),
        evidence_layers_present=layers,
        evidence_snapshot=snapshot,
        strongest_case_instruction=(
            "State the strongest good-faith conservative interpretation supported by this evidence packet. "
            "Explain the public-interest value or concern a sophisticated conservative advocate would emphasize."
        ),
        counterweight_instruction=(
            "Identify the strongest fact, tradeoff, implementation risk, or uncertainty that could weaken that conservative interpretation."
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


def build_right_lens(bill_id: str) -> RightLensIndex:
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

    result = RightLensIndex(
        schema_version="11.0",
        bill_id=bill_id,
        reviewer_version=REVIEWER_VERSION,
        source_sha256=str(anchors[0]["source_sha256"]),
        candidate_count=len(candidates),
        ready_count=sum(1 for item in candidates if item.status == "advocate_packet_ready"),
        context_needed_count=sum(1 for item in candidates if item.status == "needs_context"),
        candidates=candidates,
    )
    RIGHT_DIR.mkdir(parents=True, exist_ok=True)
    (RIGHT_DIR / f"{bill_id}.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result


def right_status() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for bill_id in PROVING_GROUND_BILLS:
        anchor_path = ANCHOR_DIR / f"{bill_id}.json"
        right_path = RIGHT_DIR / f"{bill_id}.json"
        state: dict[str, object] = {
            "citation_anchors_ready": anchor_path.exists(),
            "right_lens_ready": right_path.exists(),
            "candidate_count": 0,
            "ready_count": 0,
            "context_needed_count": 0,
            "reviewer_version": REVIEWER_VERSION,
        }
        if right_path.exists():
            payload = json.loads(right_path.read_text(encoding="utf-8"))
            state["candidate_count"] = int(payload.get("candidate_count", 0))
            state["ready_count"] = int(payload.get("ready_count", 0))
            state["context_needed_count"] = int(payload.get("context_needed_count", 0))
        result[bill_id] = state
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Pass 11 conservative advocacy review packets.")
    parser.add_argument("bill_ids", nargs="*", default=list(PROVING_GROUND_BILLS))
    args = parser.parse_args(argv)
    failed = False
    for bill_id in args.bill_ids:
        try:
            result = build_right_lens(bill_id)
            print(
                f"{bill_id}: {result.candidate_count} Right Lens packets, "
                f"{result.ready_count} ready, {result.context_needed_count} need context"
            )
        except Exception as exc:
            failed = True
            print(f"{bill_id}: ERROR - {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

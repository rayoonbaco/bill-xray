"""Pass 13: Neutral Referee for Bill X-Ray.

The referee is the evidence firewall between adversarial review and public synthesis.
It does not average the Left and Right lenses. It decides what the current record is
allowed to support, what must remain interpretation, what is disputed, what requires
more context, and what is blocked from downstream publication.

Pass 13 still does not write the public five-panel report. It produces source-bound
adjudication packets that Pass 14 must obey.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEFT_DIR = ROOT / "data" / "left_lens"
RIGHT_DIR = ROOT / "data" / "right_lens"
SKEPTIC_DIR = ROOT / "data" / "skeptic"
REFEREE_DIR = ROOT / "data" / "referee"
PROVING_GROUND_BILLS = ("aca", "obbba")
REVIEWER_VERSION = "13.0-neutral-referee"

ALLOWED_CLASSES = ("TEXT", "DIRECT_EFFECT", "LIKELY_EFFECT", "INTERPRETATION", "DISPUTED", "UNKNOWN")


@dataclass(frozen=True)
class RefereeDecision:
    schema_version: str
    reviewer_version: str
    bill_id: str
    anchor_id: str
    segment_id: str
    section_label: str
    status: str
    confidence: float
    source_symmetry_passed: bool
    evidence_layers_present: list[str]
    admissible_claim_classes: list[str]
    prohibited_claim_classes: list[str]
    text_lane: dict
    direct_effect_lane: dict
    likely_effect_lane: dict
    left_lane: dict
    right_lane: dict
    barrel_lane: dict
    unresolved_challenges: list[dict]
    required_before_publication: list[str]
    referee_rationale: list[str]
    synthesis_instruction: str
    forbidden_moves: list[str]
    location_marker: str
    document_ref: str
    source_url: str
    source_sha256: str
    text_sha256: str


@dataclass(frozen=True)
class RefereeIndex:
    schema_version: str
    bill_id: str
    reviewer_version: str
    source_sha256: str
    decision_count: int
    synthesis_ready_count: int
    context_needed_count: int
    blocked_count: int
    decisions: list[RefereeDecision]


def _load_candidates(directory: Path, bill_id: str, key: str) -> dict[str, dict]:
    path = directory / f"{bill_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Required Pass 13 input not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(item["anchor_id"]): item
        for item in payload.get(key, [])
        if item.get("anchor_id")
    }


def _require_identity(left: dict, right: dict, skeptic: dict) -> None:
    for field in ("bill_id", "anchor_id", "segment_id", "source_sha256", "text_sha256"):
        values = {str(left.get(field)), str(right.get(field)), str(skeptic.get(field))}
        if len(values) != 1:
            raise ValueError(f"Referee inputs disagree on {field}")


def _lane(status: str, claim_class: str, confidence: float, reason: str) -> dict:
    return {
        "status": status,
        "claim_class": claim_class,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "reason": reason,
    }


def build_decision(left: dict, right: dict, skeptic: dict) -> RefereeDecision:
    _require_identity(left, right, skeptic)

    same_snapshot = left.get("evidence_snapshot") == right.get("evidence_snapshot")
    same_layers = list(left.get("evidence_layers_present", [])) == list(right.get("evidence_layers_present", []))
    skeptic_symmetry = bool(skeptic.get("source_symmetry_passed"))
    symmetry = same_snapshot and same_layers and skeptic_symmetry

    layers = list(left.get("evidence_layers_present", []))
    snapshot = left.get("evidence_snapshot") or {}
    challenges = list(skeptic.get("challenges", []))
    required = list(dict.fromkeys(skeptic.get("required_resolutions", [])))
    rationale: list[str] = []

    critical = [c for c in challenges if c.get("severity") == "critical"]
    high = [c for c in challenges if c.get("severity") == "high"]
    known_context_gap = any(c.get("code") in {"KNOWN_CONTEXT_GAP", "EXTERNAL_EVIDENCE_REQUIRED"} for c in challenges)

    if not symmetry or critical:
        status = "blocked"
        confidence = 0.25
        rationale.append("The evidence record is not sufficiently symmetric or contains a critical integrity challenge.")
    elif known_context_gap or high:
        status = "needs_context"
        confidence = 0.72
        rationale.append("The source spine is intact, but one or more high-severity context gaps remain unresolved.")
    else:
        status = "synthesis_ready"
        confidence = 0.9
        rationale.append("The source spine is symmetric and no critical or high-severity blocker remains in the skeptic record.")

    text_lane = _lane(
        "admissible" if symmetry else "blocked",
        "TEXT" if symmetry else "UNKNOWN",
        0.96 if symmetry else 0.2,
        "Verified statutory text may be stated as text-level fact only within the scope of the anchored language."
        if symmetry
        else "Text-level publication is blocked until source identity and evidence symmetry are restored.",
    )

    has_money = "money" in layers
    has_power = "power" in layers
    direct_support = has_money or has_power
    direct_effect_lane = _lane(
        "admissible_with_bounds" if symmetry and direct_support else "insufficient_record",
        "DIRECT_EFFECT" if symmetry and direct_support else "UNKNOWN",
        0.86 if symmetry and direct_support else 0.52,
        "Direct legal mechanics may be stated when the extractor identifies an explicit money or authority action and the wording does not add downstream outcomes."
        if direct_support
        else "The current record does not contain a dedicated money or authority mechanic supporting a direct-effect statement.",
    )

    likely_effect_lane = _lane(
        "needs_external_evidence",
        "LIKELY_EFFECT" if symmetry else "UNKNOWN",
        0.58 if symmetry else 0.25,
        "Predicted fiscal, behavioral, distributional, implementation, or social outcomes require evidence beyond statutory text and must expose assumptions.",
    )

    advocacy_status = "admissible_as_interpretation" if symmetry else "blocked"
    advocacy_conf = min(float(left.get("confidence", 0.0)), float(right.get("confidence", 0.0)), 0.88)
    if status == "needs_context":
        advocacy_conf = min(advocacy_conf, 0.72)
    if status == "blocked":
        advocacy_conf = min(advocacy_conf, 0.3)

    left_lane = _lane(
        advocacy_status,
        "INTERPRETATION" if symmetry else "UNKNOWN",
        advocacy_conf,
        "The strongest good-faith progressive reading may be presented only as interpretation and only from the shared evidence record.",
    )
    right_lane = _lane(
        advocacy_status,
        "INTERPRETATION" if symmetry else "UNKNOWN",
        advocacy_conf,
        "The strongest good-faith conservative reading may be presented only as interpretation and only from the shared evidence record.",
    )

    if "barrel_scan" in snapshot:
        barrel_lane = _lane(
            "admissible_as_scrutiny_flag" if symmetry else "blocked",
            "DIRECT_EFFECT" if symmetry else "UNKNOWN",
            0.82 if symmetry else 0.25,
            "The detector may explain why a provision deserves scrutiny, but the flag does not establish motive, waste, favoritism, illegality, or corruption.",
        )
    else:
        barrel_lane = _lane(
            "no_candidate",
            "UNKNOWN",
            0.9 if symmetry else 0.25,
            "No Barrel Scan candidate is present in the joined evidence snapshot for this anchor.",
        )

    admissible = ["TEXT"] if symmetry else []
    if symmetry and direct_support:
        admissible.append("DIRECT_EFFECT")
    if symmetry:
        admissible.append("INTERPRETATION")
    if symmetry and status != "blocked":
        admissible.extend(["DISPUTED", "UNKNOWN"])
    admissible = list(dict.fromkeys(admissible))
    prohibited = [item for item in ALLOWED_CLASSES if item not in admissible]
    if symmetry:
        # LIKELY_EFFECT remains a legal class, but Pass 13 refuses to admit it without
        # external evidence. It is therefore prohibited for current synthesis packets.
        if "LIKELY_EFFECT" not in prohibited:
            prohibited.append("LIKELY_EFFECT")

    if "citation_anchor" in layers:
        rationale.append("All lanes remain bound to the same verified Pass 4 citation anchor.")
    if has_money:
        rationale.append("Money-extractor evidence is available for bounded direct fiscal mechanics, not ultimate budget incidence by itself.")
    if has_power:
        rationale.append("Power-extractor evidence is available for bounded authority mechanics, not constitutionality or predicted use by itself.")
    if "barrel_scan" in snapshot:
        rationale.append("Barrel Scan output is preserved only as a scrutiny signal, never as a misconduct finding.")
    rationale.append("Left and Right agreement cannot upgrade a claim class; disagreement cannot downgrade anchored statutory text.")

    if status == "synthesis_ready":
        synthesis_instruction = (
            "Pass 14 may use this anchor, but each public sentence must stay inside the admitted claim class, "
            "retain a citation, and preserve LEFT/RIGHT interpretation labels."
        )
    elif status == "needs_context":
        synthesis_instruction = (
            "Pass 14 may use only bounded TEXT or DIRECT_EFFECT material that does not depend on unresolved context. "
            "Do not publish stronger downstream-effect claims from this packet."
        )
    else:
        synthesis_instruction = "Pass 14 must not publish claims from this anchor until the referee block is resolved."

    return RefereeDecision(
        schema_version="13.0",
        reviewer_version=REVIEWER_VERSION,
        bill_id=str(left["bill_id"]),
        anchor_id=str(left["anchor_id"]),
        segment_id=str(left["segment_id"]),
        section_label=str(left.get("section_label") or right.get("section_label") or ""),
        status=status,
        confidence=round(confidence, 3),
        source_symmetry_passed=symmetry,
        evidence_layers_present=layers,
        admissible_claim_classes=admissible,
        prohibited_claim_classes=prohibited,
        text_lane=text_lane,
        direct_effect_lane=direct_effect_lane,
        likely_effect_lane=likely_effect_lane,
        left_lane=left_lane,
        right_lane=right_lane,
        barrel_lane=barrel_lane,
        unresolved_challenges=challenges,
        required_before_publication=required,
        referee_rationale=rationale,
        synthesis_instruction=synthesis_instruction,
        forbidden_moves=[
            "Do not average LEFT and RIGHT into a false middle position.",
            "Do not upgrade advocacy agreement into TEXT or DIRECT_EFFECT.",
            "Do not downgrade clear statutory language because an advocacy lane disputes it.",
            "Do not publish LIKELY_EFFECT without external evidence appropriate to the asserted outcome.",
            "Do not convert a Barrel Scan flag into corruption, waste, favoritism, illegality, or motive.",
            "Do not hide unresolved context gaps behind confident prose.",
            "Do not admit any consequential public claim without its verified citation anchor.",
        ],
        location_marker=str(left.get("location_marker", "")),
        document_ref=str(left.get("document_ref", "")),
        source_url=str(left.get("source_url", "")),
        source_sha256=str(left["source_sha256"]),
        text_sha256=str(left["text_sha256"]),
    )


def build_referee_review(bill_id: str) -> RefereeIndex:
    left = _load_candidates(LEFT_DIR, bill_id, "candidates")
    right = _load_candidates(RIGHT_DIR, bill_id, "candidates")
    skeptic = _load_candidates(SKEPTIC_DIR, bill_id, "packets")

    sets = (set(left), set(right), set(skeptic))
    if not (sets[0] == sets[1] == sets[2]):
        raise ValueError("Left, Right, and Skeptic anchor sets must be identical before referee review")
    if not left:
        raise ValueError(f"No paired advocacy/skeptic packets available for {bill_id}")

    decisions = [build_decision(left[anchor_id], right[anchor_id], skeptic[anchor_id]) for anchor_id in sorted(left)]
    result = RefereeIndex(
        schema_version="13.0",
        bill_id=bill_id,
        reviewer_version=REVIEWER_VERSION,
        source_sha256=decisions[0].source_sha256,
        decision_count=len(decisions),
        synthesis_ready_count=sum(1 for item in decisions if item.status == "synthesis_ready"),
        context_needed_count=sum(1 for item in decisions if item.status == "needs_context"),
        blocked_count=sum(1 for item in decisions if item.status == "blocked"),
        decisions=decisions,
    )
    REFEREE_DIR.mkdir(parents=True, exist_ok=True)
    (REFEREE_DIR / f"{bill_id}.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result


def referee_status() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for bill_id in PROVING_GROUND_BILLS:
        path = REFEREE_DIR / f"{bill_id}.json"
        state: dict[str, object] = {
            "referee_ready": path.exists(),
            "decision_count": 0,
            "synthesis_ready_count": 0,
            "context_needed_count": 0,
            "blocked_count": 0,
            "reviewer_version": REVIEWER_VERSION,
        }
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            state["decision_count"] = int(payload.get("decision_count", 0))
            state["synthesis_ready_count"] = int(payload.get("synthesis_ready_count", 0))
            state["context_needed_count"] = int(payload.get("context_needed_count", 0))
            state["blocked_count"] = int(payload.get("blocked_count", 0))
        result[bill_id] = state
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Pass 13 Neutral Referee adjudication packets.")
    parser.add_argument("bill_ids", nargs="*", default=list(PROVING_GROUND_BILLS))
    args = parser.parse_args(argv)
    failed = False
    for bill_id in args.bill_ids:
        try:
            result = build_referee_review(bill_id)
            print(
                f"{bill_id}: {result.decision_count} referee decisions, "
                f"{result.synthesis_ready_count} synthesis-ready, "
                f"{result.context_needed_count} need context, {result.blocked_count} blocked"
            )
        except Exception as exc:
            failed = True
            print(f"{bill_id}: ERROR - {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

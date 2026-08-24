"""Pass 12: Investigative Skeptic review for Bill X-Ray.

The skeptic is an internal adversarial quality-control layer. It receives the Left
and Right advocacy packets for the same verified citation anchor, checks that both
lanes were built from the same source-bound evidence spine, inventories missing
context, and creates explicit challenges that the Neutral Referee must resolve.

This pass does not choose a political side and does not publish final claims.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANCHOR_DIR = ROOT / "data" / "citation_anchors"
LEFT_DIR = ROOT / "data" / "left_lens"
RIGHT_DIR = ROOT / "data" / "right_lens"
SKEPTIC_DIR = ROOT / "data" / "skeptic"
PROVING_GROUND_BILLS = ("aca", "obbba")
REVIEWER_VERSION = "12.0-investigative-skeptic"


@dataclass(frozen=True)
class SkepticPacket:
    schema_version: str
    reviewer_version: str
    bill_id: str
    anchor_id: str
    segment_id: str
    section_label: str
    claim_class: str
    status: str
    confidence: float
    source_symmetry_passed: bool
    shared_evidence_layers: list[str]
    left_only_layers: list[str]
    right_only_layers: list[str]
    challenges: list[dict]
    required_resolutions: list[str]
    referee_instruction: str
    forbidden_moves: list[str]
    location_marker: str
    document_ref: str
    source_url: str
    source_sha256: str
    text_sha256: str


@dataclass(frozen=True)
class SkepticIndex:
    schema_version: str
    bill_id: str
    reviewer_version: str
    source_sha256: str
    packet_count: int
    ready_count: int
    blocked_count: int
    packets: list[SkepticPacket]


def _challenge(code: str, severity: str, message: str, resolution: str) -> dict:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "resolution": resolution,
    }


def _require_same_identity(left: dict, right: dict) -> None:
    for field in ("bill_id", "anchor_id", "segment_id", "source_sha256", "text_sha256"):
        if str(left.get(field)) != str(right.get(field)):
            raise ValueError(f"Left/Right advocacy packets disagree on {field}")


def build_packet(left: dict, right: dict) -> SkepticPacket:
    _require_same_identity(left, right)

    anchor_id = str(left["anchor_id"])
    left_layers = set(left.get("evidence_layers_present", []))
    right_layers = set(right.get("evidence_layers_present", []))
    shared = sorted(left_layers & right_layers)
    left_only = sorted(left_layers - right_layers)
    right_only = sorted(right_layers - left_layers)

    same_snapshot = left.get("evidence_snapshot") == right.get("evidence_snapshot")
    same_provenance = (
        left.get("source_sha256") == right.get("source_sha256")
        and left.get("text_sha256") == right.get("text_sha256")
        and left.get("document_ref") == right.get("document_ref")
        and left.get("source_url") == right.get("source_url")
    )
    symmetry = same_snapshot and same_provenance and not left_only and not right_only

    challenges: list[dict] = []
    required: list[str] = []

    if not symmetry:
        challenges.append(_challenge(
            "ASYMMETRIC_EVIDENCE",
            "critical",
            "The Left and Right lanes are not operating from an identical evidence record.",
            "Rebuild both advocacy packets from the same verified anchor and identical joined evidence before comparing them.",
        ))
        required.append("Restore identical source-bound evidence for both advocacy lanes.")

    if left.get("claim_class") != "INTERPRETATION" or right.get("claim_class") != "INTERPRETATION":
        challenges.append(_challenge(
            "CLASSIFICATION_DRIFT",
            "critical",
            "An advocacy lane is no longer explicitly classified as INTERPRETATION.",
            "Return both advocacy lanes to INTERPRETATION unless later adjudicated evidence supports a different allowed class.",
        ))
        required.append("Keep advocacy separate from statutory fact.")

    statuses = {str(left.get("status")), str(right.get("status"))}
    if "needs_context" in statuses:
        challenges.append(_challenge(
            "KNOWN_CONTEXT_GAP",
            "high",
            "At least one advocacy lane already acknowledges missing fiscal, legal, distributional, implementation, or topic context.",
            "Obtain or explicitly preserve the missing context before allowing a strong public-facing interpretation.",
        ))
        required.append("Resolve acknowledged context gaps or carry them forward visibly.")

    external = list(dict.fromkeys(
        list(left.get("external_evidence_needed", []))
        + list(right.get("external_evidence_needed", []))
    ))
    if external:
        challenges.append(_challenge(
            "EXTERNAL_EVIDENCE_REQUIRED",
            "high",
            "The advocacy record itself identifies claims that would require evidence beyond the statutory text.",
            "Do not permit downstream claims about fiscal size, beneficiaries, outcomes, motive, or legal consequence until the identified evidence is supplied.",
        ))
        required.extend(external)

    snapshot = left.get("evidence_snapshot") or {}
    if "barrel_scan" in snapshot:
        challenges.append(_challenge(
            "BARREL_FLAG_OVERREACH",
            "high",
            "A Barrel Scan candidate is present, which can tempt either side to imply favoritism, waste, hidden intent, or corruption.",
            "Treat the flag only as a reason for scrutiny. Require independent evidence for motive, impropriety, or beneficiary effects.",
        ))
        required.append("Keep Barrel Scan flags separate from misconduct findings.")

    if "citation_anchor" in shared and len(shared) == 1:
        challenges.append(_challenge(
            "THIN_EVIDENCE_RECORD",
            "medium",
            "The advocacy lanes currently rely only on the statutory anchor and have no joined money, power, or topic-review context.",
            "Limit claims to what this evidence can support; add specialist or fiscal context before making broader effect claims.",
        ))
        required.append("Do not let a single statutory excerpt carry downstream effect claims by itself.")

    challenges.extend([
        _challenge(
            "CAUSAL_LEAP_CHECK",
            "medium",
            "Policy advocacy often turns statutory mechanics into predicted outcomes without enough causal evidence.",
            "For every downstream outcome claim, demand a cited mechanism and evidence appropriate to that claim class.",
        ),
        _challenge(
            "RHETORICAL_INFLATION_CHECK",
            "medium",
            "Strong advocacy can overstate certainty, scale, beneficiaries, or harm even when the underlying concern is legitimate.",
            "Match wording strength to evidence strength and confidence; downgrade or reject language that outruns the record.",
        ),
        _challenge(
            "CHERRY_PICKING_CHECK",
            "medium",
            "A provision can look different when definitions, exceptions, effective dates, and cross-references are considered.",
            "Verify material qualifiers and connected provisions before treating the excerpt as representative of the full legal mechanic.",
        ),
    ])

    status = "skeptic_packet_ready" if symmetry else "blocked_asymmetric_record"
    confidence = 0.92 if symmetry else 0.35
    if symmetry and "needs_context" in statuses:
        confidence = 0.78

    return SkepticPacket(
        schema_version="12.0",
        reviewer_version=REVIEWER_VERSION,
        bill_id=str(left["bill_id"]),
        anchor_id=anchor_id,
        segment_id=str(left["segment_id"]),
        section_label=str(left.get("section_label") or right.get("section_label") or ""),
        claim_class="UNKNOWN",
        status=status,
        confidence=round(confidence, 3),
        source_symmetry_passed=symmetry,
        shared_evidence_layers=shared,
        left_only_layers=left_only,
        right_only_layers=right_only,
        challenges=challenges,
        required_resolutions=list(dict.fromkeys(required)),
        referee_instruction=(
            "Do not decide which advocacy lane is more persuasive. Determine which specific assertions survive the evidence, "
            "which remain interpretation, which are disputed, and which must be rejected or downgraded."
        ),
        forbidden_moves=[
            "Do not reward a claim because it is rhetorically compelling or politically familiar.",
            "Do not convert absence of evidence into evidence of absence or wrongdoing.",
            "Do not treat a Barrel Scan flag as proof of corruption, waste, favoritism, or hidden motive.",
            "Do not allow either advocacy lane to receive facts the other lane did not receive.",
            "Do not publish a skeptic accusation; this is an internal challenge record for the referee.",
        ],
        location_marker=str(left.get("location_marker", "")),
        document_ref=str(left.get("document_ref", "")),
        source_url=str(left.get("source_url", "")),
        source_sha256=str(left["source_sha256"]),
        text_sha256=str(left["text_sha256"]),
    )


def _load_candidates(directory: Path, bill_id: str) -> dict[str, dict]:
    path = directory / f"{bill_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Advocacy packets not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(item["anchor_id"]): item
        for item in payload.get("candidates", [])
        if item.get("anchor_id")
    }


def build_skeptic_review(bill_id: str) -> SkepticIndex:
    left = _load_candidates(LEFT_DIR, bill_id)
    right = _load_candidates(RIGHT_DIR, bill_id)
    if set(left) != set(right):
        missing_left = sorted(set(right) - set(left))
        missing_right = sorted(set(left) - set(right))
        raise ValueError(
            f"Left/Right anchor sets differ; missing_left={missing_left}, missing_right={missing_right}"
        )
    if not left:
        raise ValueError(f"No paired advocacy packets available for {bill_id}")

    packets = [build_packet(left[anchor_id], right[anchor_id]) for anchor_id in sorted(left)]
    result = SkepticIndex(
        schema_version="12.0",
        bill_id=bill_id,
        reviewer_version=REVIEWER_VERSION,
        source_sha256=packets[0].source_sha256,
        packet_count=len(packets),
        ready_count=sum(1 for item in packets if item.status == "skeptic_packet_ready"),
        blocked_count=sum(1 for item in packets if item.status != "skeptic_packet_ready"),
        packets=packets,
    )
    SKEPTIC_DIR.mkdir(parents=True, exist_ok=True)
    (SKEPTIC_DIR / f"{bill_id}.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result


def skeptic_status() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for bill_id in PROVING_GROUND_BILLS:
        left_path = LEFT_DIR / f"{bill_id}.json"
        right_path = RIGHT_DIR / f"{bill_id}.json"
        skeptic_path = SKEPTIC_DIR / f"{bill_id}.json"
        state: dict[str, object] = {
            "left_lens_ready": left_path.exists(),
            "right_lens_ready": right_path.exists(),
            "skeptic_ready": skeptic_path.exists(),
            "packet_count": 0,
            "ready_count": 0,
            "blocked_count": 0,
            "reviewer_version": REVIEWER_VERSION,
        }
        if skeptic_path.exists():
            payload = json.loads(skeptic_path.read_text(encoding="utf-8"))
            state["packet_count"] = int(payload.get("packet_count", 0))
            state["ready_count"] = int(payload.get("ready_count", 0))
            state["blocked_count"] = int(payload.get("blocked_count", 0))
        result[bill_id] = state
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Pass 12 Investigative Skeptic review packets.")
    parser.add_argument("bill_ids", nargs="*", default=list(PROVING_GROUND_BILLS))
    args = parser.parse_args(argv)
    failed = False
    for bill_id in args.bill_ids:
        try:
            result = build_skeptic_review(bill_id)
            print(
                f"{bill_id}: {result.packet_count} skeptic packets, "
                f"{result.ready_count} ready, {result.blocked_count} blocked"
            )
        except Exception as exc:
            failed = True
            print(f"{bill_id}: ERROR - {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(rel: str, bill_id: str) -> dict:
    path = ROOT / "data" / rel / f"{bill_id}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    bill_id = sys.argv[1] if len(sys.argv) > 1 else "gpo-118hr171ih"
    translations = load("translations", bill_id).get("translations", [])
    topics = load("topic_reviews", bill_id).get("reviews", [])
    power = load("power", bill_id).get("findings", [])
    synthesis = load("synthesis", bill_id)
    analysis = load("analyses", bill_id)

    print("=" * 72)
    print(" BILL X-RAY - PASS 31.6.2.4 MAIN-EFFECT / EXPERT-CONTEXT FORENSICS")
    print("=" * 72)
    print(f"Bill: {bill_id}")
    print(f"Analysis status: {analysis.get('analysis_status', synthesis.get('analysis_status', 'missing'))}")
    print(f"Missing public lanes: {', '.join(synthesis.get('missing_public_lanes', [])) or 'none'}")
    print()

    print("Translation disposition:")
    for item in translations:
        print(f"  {item.get('section_label')} | {item.get('status')} | confidence={item.get('confidence')}")
        if item.get("review_reason"):
            print(f"    reason: {item.get('review_reason')}")
    print()

    print("Topic routing:")
    for item in topics:
        print(f"  {item.get('section_label')} | {item.get('status')} | primary={item.get('primary_domain')} | domains={', '.join(item.get('expert_domains', []))}")
        for needed in item.get("context_needed", []):
            print(f"    context: {needed}")
    print()

    print("Authority packet guard:")
    for item in power:
        actors = ", ".join(item.get("actors", [])) or "none"
        print(f"  {item.get('section_label')} | {item.get('status')} | extracted actors={actors}")
    print()

    sec3_t = next((x for x in translations if x.get("section_label") == "SEC. 3"), {})
    sec3_r = next((x for x in topics if x.get("section_label") == "SEC. 3"), {})
    print("Forensic conclusion:")
    if sec3_t.get("status") == "translated":
        print("  SECTION 3 NO LONGER FAILS THE TRANSLATOR'S QUALIFIER-INTEGRITY CHECK.")
    else:
        print("  SECTION 3 IS STILL HELD BY THE TRANSLATOR.")
    if sec3_r.get("status") == "expert_review_packet_ready":
        print("  THE 'TOPIC EXPERT' STAGE HAS PRODUCED A ROUTING/REVIEW PACKET, NOT A SUBSTANTIVE EXPERT ANSWER.")
        print("  Its artifact contains domains, questions, evidence snapshots, and context-needed flags; it does not resolve them into a public main-effect claim.")
    print("  Therefore a remaining empty WHAT IT REALLY DOES lane is not safe to solve by lowering thresholds.")
    print("  The next architecture decision is a bounded, source-reproducible section-effect resolver (or a real expert execution layer).")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

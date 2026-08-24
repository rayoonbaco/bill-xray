from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BILL_ID = "gpo-118hr171ih"


def load(rel: str) -> dict:
    path = ROOT / rel / f"{BILL_ID}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    print("=" * 72)
    print(" BILL X-RAY - PASS 31.6.2.3 FRESH-BILL RELEASE-HOLD FORENSICS")
    print("=" * 72)
    synthesis = load("data/synthesis")
    end_to_end = load("data/end_to_end")
    segments = load("data/segments")
    translations = load("data/translations")
    power = load("data/power")
    money = load("data/money")

    if not synthesis:
        print(f"{BILL_ID}: no synthesis artifact found. Rebuild the bill first.")
        return 2

    print(f"Bill: {BILL_ID}")
    print(f"Analysis status: {synthesis.get('analysis_status')}")
    print(f"Missing public lanes: {', '.join(synthesis.get('missing_public_lanes', [])) or 'none'}")
    print(f"Public claims selected: {synthesis.get('selected_count', 0)}")
    print(f"Red team: {end_to_end.get('red_team_status', 'unknown')}")
    print(f"Citation audit: {end_to_end.get('citation_audit_status', 'unknown')}")
    print(f"Hostile challenge: {end_to_end.get('challenge_status', 'unknown')}")

    print("\nStructural sections:")
    for item in segments.get("segments", []):
        if item.get("kind") == "section":
            print(f"  SEC. {item.get('identifier')} | lines {item.get('start_line')}-{item.get('end_line')} | {item.get('heading')}")

    translated = translations.get("translations", [])
    print("\nTranslation disposition:")
    for item in translated:
        text = " ".join(str(item.get("plain_english") or "").split())
        print(f"  {item.get('section_label') or item.get('segment_id')} | {item.get('status')} | plain chars={len(text)}")

    print("\nAuthority findings:")
    for item in power.get("findings", []):
        print(f"  {item.get('section_label')} | {item.get('status')} | {', '.join(item.get('authority_types', [])) or 'none'}")

    print("\nMoney findings:")
    if not money.get("findings"):
        print("  none")
    for item in money.get("findings", []):
        print(f"  {item.get('section_label')} | {item.get('status')} | explicit amounts={len(item.get('amounts', []))}")

    print("\nForensic conclusion:")
    missing = synthesis.get("missing_public_lanes", [])
    if "what_it_really_does" in missing:
        print("  RELEASE HOLD IS CAUSED BY THE EMPTY 'WHAT IT REALLY DOES' PUBLIC LANE.")
        print("  The later red-team, citation-audit, and hostile-context gates are not the blocker.")
        print("  Do not weaken the release gate. Diagnose why no substantive main-effect claim qualifies.")
    else:
        print("  The main-effect lane is present; inspect the other missing lane(s) above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

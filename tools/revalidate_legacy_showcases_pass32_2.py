"""Pass 32.2: rebuild legacy ACA/OBBBA showcases through the current parser and gates.

The existing persistent release is never replaced until the newly rebuilt working
artifacts clear every current release gate and the legacy SECTION/TION artifact is gone.
If a rebuild is held or errors, the prior verified persistent release is restored into
working data so a failed revalidation cannot silently degrade the public museum.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.aca_end_to_end import run_aca
from engine.obbba_end_to_end import run_obbba
from engine.showcase_release import (
    persistent_release_status,
    publish_verified_showcase,
    restore_verified_showcase,
)

BILLS = (("aca", "Affordable Care Act", run_aca), ("obbba", "One Big Beautiful Bill Act", run_obbba))
REPORT = ROOT / "PASS32_2_REVALIDATION_REPORT.txt"


def suspicious_anchor_count(bill_id: str) -> tuple[int, int]:
    path = ROOT / "data" / "citation_anchors" / f"{bill_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    anchors = payload.get("anchors") or []
    bad = 0
    for anchor in anchors:
        if not isinstance(anchor, dict):
            continue
        ident = str(anchor.get("identifier") or anchor.get("section_identifier") or "")
        label = str(anchor.get("section_label") or "")
        if ident.upper() == "TION" or "SEC. TION" in label.upper():
            bad += 1
    return len(anchors), bad


def release_ok(result: dict) -> bool:
    return (
        result.get("analysis_status") == "verified"
        and result.get("red_team_status") != "fail"
        and result.get("citation_audit_status") != "fail"
        and result.get("challenge_status") != "fail"
        and int(result.get("red_team_critical_count", 0) or 0) == 0
        and int(result.get("citation_audit_critical_count", 0) or 0) == 0
        and int(result.get("challenge_blocker_count", 0) or 0) == 0
    )


def main() -> int:
    lines: list[str] = []
    failures = 0
    print("=" * 72)
    print(" BILL X-RAY - PASS 32.2 LEGACY EXHIBIT REVALIDATION")
    print("=" * 72)
    print("ACA and OBBBA will be rebuilt through the current 19-stage pipeline.")
    print("Their existing persistent exhibits remain untouched until a new build clears every gate.\n")

    for bill_id, title, runner in BILLS:
        print(f"\n=== {title} ===")
        prior = persistent_release_status(bill_id)
        print(f"Prior persistent release: {prior.get('state')} | {prior.get('store')}")
        try:
            result = runner()
            total, suspicious = suspicious_anchor_count(bill_id)
            print(f"Current citation anchors: {total:,}; suspicious SECTION/TION anchors: {suspicious}")
            gates = release_ok(result)
            if gates and suspicious == 0:
                published = publish_verified_showcase(bill_id)
                msg = (
                    f"[VERIFIED] {title}: rebuilt with current segmentation; "
                    f"{total:,} anchors; 0 SECTION/TION artifacts; all release gates cleared; "
                    f"persistent exhibit atomically replaced at {published['store']}."
                )
                print(msg)
                lines.append(msg)
            else:
                failures += 1
                restored = restore_verified_showcase(bill_id)
                msg = (
                    f"[HOLD] {title}: new build did not earn replacement. "
                    f"analysis={result.get('analysis_status')} red={result.get('red_team_status')} "
                    f"audit={result.get('citation_audit_status')} challenge={result.get('challenge_status')} "
                    f"suspicious_anchors={suspicious}. Prior verified release restored={restored.get('restored')}."
                )
                print(msg)
                lines.append(msg)
        except Exception as exc:
            failures += 1
            restored = restore_verified_showcase(bill_id)
            msg = f"[ERROR] {title}: {type(exc).__name__}: {exc}. Prior verified release restored={restored.get('restored')}."
            print(msg)
            lines.append(msg)

    verdict = (
        "PASS 32.2 RESULT: ACA and OBBBA were revalidated through the current parser and release gates."
        if failures == 0
        else "PASS 32.2 RESULT: At least one legacy exhibit did not earn replacement. Do not launch yet."
    )
    print("\n" + "=" * 72)
    print(verdict)
    print("=" * 72)
    lines.append(verdict)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report: {REPORT}")
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Pass 31.6.1: refresh only the supplemental CBO/external-context lane.

The verified statutory analysis and its release-gate artifacts are restored first and
never recomputed here. A persistent showcase is republished only when a verified CBO
match is found; otherwise the previous persistent exhibit remains untouched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Resolve the Bill X-Ray project root from this script, not from the caller's
# current working directory. This makes the refresh launcher safe to invoke
# from Explorer, another shell directory, or automation.
ROOT = Path(__file__).resolve().parents[1]
ROOT_STR = str(ROOT)
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)

from engine import consequence, external_evidence
from engine.showcase_release import publish_verified_showcase, restore_verified_showcase, persistent_release_status
BILLS = ("aca", "obbba")


def _print_cbo(bill_id: str, cbo: dict) -> None:
    print(f"  CBO status: {cbo.get('status')}")
    selected = cbo.get("selected") or {}
    if selected:
        print(f"  Selected: {selected.get('title')}")
        print(f"  URL: {selected.get('url')}")
        print(f"  Identity confidence: {selected.get('identity_confidence')}")
        basis = selected.get("identity_basis") or []
        if basis:
            print("  Identity basis: " + "; ".join(str(x) for x in basis))
    for diag in cbo.get("diagnostics") or []:
        print(f"  [{diag.get('method')}] {diag.get('status')} | candidates={diag.get('candidate_count', 0)} | {diag.get('url')}")
        if diag.get("detail"):
            print(f"      {diag.get('detail')}")


def main() -> int:
    print("BILL X-RAY · PASS 31.6.1.1 CBO REFRESH LAUNCHER IMPORT REPAIR")
    print(f"Project root: {ROOT}")
    print("Only supplemental official external context is refreshed. The verified statutory analysis is frozen.\n")
    published = 0
    for bill_id in BILLS:
        print(f"=== {bill_id.upper()} ===")
        status = persistent_release_status(bill_id)
        if status.get("state") != "verified":
            print(f"  STOP: persistent showcase is not verified ({status.get('state')}). Nothing changed.")
            continue
        restore = restore_verified_showcase(bill_id)
        if not restore.get("restored"):
            print("  STOP: verified exhibit could not be restored. Nothing changed.")
            continue
        payload = external_evidence.collect_external_evidence(bill_id)
        cbo = payload.get("lanes", {}).get("cbo", {})
        _print_cbo(bill_id, cbo)
        if cbo.get("status") != "found":
            print("  NOT PUBLISHED: CBO could not be verified automatically; prior persistent exhibit remains untouched.\n")
            continue
        consequence.build_consequence_context(bill_id)
        pub = publish_verified_showcase(bill_id)
        published += 1
        print(f"  [ATOMIC PUBLISH] refreshed external context -> {pub.get('store')}\n")
    print("========================================")
    print(f" {published} / 2 SHOWCASES REFRESHED WITH VERIFIED CBO CONTEXT")
    print("========================================")
    print("A non-refreshed showcase remains on its prior verified persistent release.")
    return 0


if __name__ == "__main__":
    if "--import-check" in sys.argv:
        print("PASS 31.6.1.1 import check: OK")
        print(f"Project root: {ROOT}")
        raise SystemExit(0)
    raise SystemExit(main())

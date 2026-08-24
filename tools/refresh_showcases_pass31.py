"""Pass 31: refresh only the public consequence layer for verified showcase bills.

This is intentionally much cheaper than the 19-stage source build. It reuses the
already-generated source-bound intermediate artifacts, reruns Barrel Scan with the
canonical fiscal ontology, rebuilds public synthesis, then reruns the three release
gates before publishing a new persistent Pass-31 showcase release.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import barrel_scan, synthesis, red_team, audit, challenge
from engine.showcase_release import publish_verified_showcase

REQUIRED = ("citation_anchors", "translations", "money", "power", "left_lens", "right_lens", "referee")


def refresh_one(bill_id: str) -> None:
    missing = [name for name in REQUIRED if not (ROOT / "data" / name / f"{bill_id}.json").exists()]
    if missing:
        raise RuntimeError(f"{bill_id}: cannot do presentation-only refresh; missing intermediate artifacts: {', '.join(missing)}")
    print(f"\n=== {bill_id.upper()} · PASS 31 PRESENTATION REFRESH ===", flush=True)
    b = barrel_scan.scan_bill(bill_id, write=True)
    print(f"Barrel Scan: {b.candidate_count:,} candidates; canonical fiscal signal active", flush=True)
    s = synthesis.synthesize_bill(bill_id, write=True)
    print(f"Public synthesis: {s.analysis_status}; {s.selected_count} claims", flush=True)
    r = red_team.audit_analysis(bill_id, write=True)
    print(f"Red team: {r.status}; score={r.score:.3f}; critical={r.critical_count}", flush=True)
    a = audit.audit_bill(bill_id, write=True)
    print(f"Citation audit: {a.status}; {a.citations_checked}/{a.public_claim_count} citations checked", flush=True)
    c = challenge.audit_analysis(bill_id, write=True)
    print(f"Hostile context: {c.status}; score={c.score:.3f}; blockers={c.blocker_count}", flush=True)
    if s.analysis_status != "verified" or r.critical_count or a.critical_count or c.blocker_count:
        raise RuntimeError(f"{bill_id}: Pass 31 presentation refresh did not clear every release gate")
    published = publish_verified_showcase(bill_id)
    print(f"[VERIFIED] {bill_id.upper()} Pass-31 persistent exhibit: {published['store']}", flush=True)


def main() -> int:
    print("BILL X-RAY · PASS 31 SHOWCASE PRESENTATION REFRESH", flush=True)
    print("Reuses verified source/intermediate artifacts. No GovInfo refetch and no full 19-stage rebuild.", flush=True)
    try:
        for bill_id in ("aca", "obbba"):
            refresh_one(bill_id)
    except Exception as exc:
        print(f"\nREFRESH STOPPED SAFELY: {exc}", flush=True)
        print("Nothing is force-published.", flush=True)
        return 2
    print("\n2 / 2 PASS-31 SHOWCASES REFRESHED AND PERSISTED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

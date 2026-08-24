"""Pass 31: explicit schema-reconciled showcase handoff diagnostics."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from engine.showcase_release import persistent_store_root, restore_all_showcases, reconcile_working_release
from engine.build_orchestrator import build_status

print(f"Project root: {ROOT}")
print(f"Persistent showcase store: {persistent_store_root()}")
results = restore_all_showcases()
for bill_id in ("aca", "obbba"):
    restore = results[bill_id]
    status = build_status(bill_id)
    report = restore.get("reconciliation") or reconcile_working_release(bill_id)
    label = bill_id.upper()
    print(f"{label} persistent release: {restore.get('state', 'missing').upper()} | restored={restore.get('restored', False)} | runtime={status.get('state')}")
    if restore.get("adopted_from_working_folder"):
        print(f"  {label} migration: VERIFIED artifacts reconciled and copied into persistent store")
    if not report.get("adoptable"):
        missing = report.get("missing_physical_artifacts") or []
        failures = report.get("failures") or []
        if missing:
            print(f"  {label} physical artifacts missing: {', '.join(missing)}")
        print(f"  {label} reconciliation failures: {', '.join(failures) if failures else 'none'}")
        print(f"  {label} normalized statuses: {report.get('normalized')}")
    if status.get("state") == "verified":
        print(f"  {label} verified release: FOUND")
    elif restore.get("state") == "invalid":
        print(f"  {label} verified release: INVALID ({restore.get('reason', 'unknown reason')})")
    else:
        print(f"  {label} verified release: NOT AVAILABLE")

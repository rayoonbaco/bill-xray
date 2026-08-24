"""Pass 32: prebuild the four curated public showcase reports safely.

This helper uses the exact same public build orchestrator as the web UI. It does not
bypass referee, red-team, citation, context, or any other release gate. A held or
failed report stops the sequence and remains unpublished.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# When Python executes ``tools/prebuild_showcases.py`` directly, sys.path[0] is the
# tools directory. Add the application root explicitly before importing ``engine``.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.build_orchestrator import build_status, start_build  # noqa: E402
from engine.showcase_release import publish_verified_showcase, persistent_store_root  # noqa: E402

SHOWCASES = (
    ("aca", "Affordable Care Act"),
    ("ira", "Inflation Reduction Act"),
    ("tcja", "Tax Cuts and Jobs Act"),
    ("obbba", "One Big Beautiful Bill Act"),
)
TERMINAL = {"verified", "hold", "error"}


def _detail(status: dict) -> str:
    """Return the most useful available terminal diagnostic without inventing one."""
    for key in ("message", "hold_reason", "error", "detail"):
        value = status.get(key)
        if value:
            return str(value)
    progress = status.get("progress") or {}
    for key in ("message", "stage_label"):
        value = progress.get(key)
        if value:
            return str(value)
    return "No additional diagnostic was returned."


def build_one(bill_id: str, title: str) -> tuple[bool, str, str]:
    status = build_status(bill_id)
    state = status.get("state")
    if state == "verified":
        publish_verified_showcase(bill_id)
        print(f"[VERIFIED] {title}: verified cache already present - persistent instant exhibit ready.")
        return True, "verified", "Verified cache already present and published to persistent showcase store."

    print(f"\n=== {title} ===")
    print("Starting full 19-check public pipeline...")
    start_build(bill_id)
    last_signature = None

    while True:
        status = build_status(bill_id)
        state = str(status.get("state") or "")
        progress = status.get("progress") or {}
        stage = progress.get("stage_label") or progress.get("stage") or "Working"
        step = progress.get("step") or progress.get("stage_number")
        total = progress.get("total_steps") or progress.get("stage_total") or 19
        percent = progress.get("percent", 0)
        signature = (stage, step, percent)

        if signature != last_signature:
            step_text = f"{step}/{total}" if step else f"{percent}%"
            print(f"  {str(percent) + '%':>5}  [{step_text}] {stage}")
            last_signature = signature

        if state in TERMINAL:
            detail = _detail(status)
            if state == "verified":
                published = publish_verified_showcase(bill_id)
                print(f"[VERIFIED] {title}: all release gates cleared.")
                print(f"           Persistent exhibit published: {published['store']}")
                return True, state, detail
            if state == "hold":
                print(f"[REVIEW HOLD] {title}: {detail}")
                return False, state, detail
            print(f"[ERROR] {title}: {detail}")
            return False, state or "error", detail

        time.sleep(1.5)


def main() -> int:
    print("BILL X-RAY - PREBUILD PUBLIC SHOWCASES")
    print(f"Project root: {ROOT}")
    print(f"Persistent showcase store: {persistent_store_root()}")
    print("These builds use every normal release gate and may take 10-20 minutes each.")
    print("A held report stays held. Nothing is force-published.\n")

    results: list[tuple[str, str, str]] = []
    for bill_id, title in SHOWCASES:
        ok, state, detail = build_one(bill_id, title)
        results.append((title, state, detail))

    print("\n========================================")
    print(" BILL X-RAY SHOWCASE PREBUILD RESULT")
    print("========================================")
    for title, state, detail in results:
        label = "VERIFIED" if state == "verified" else "REVIEW HOLD" if state == "hold" else "ERROR"
        print(f"[{label}] {title}")
        if state != "verified":
            print(f"           {detail}")

    if len(results) == len(SHOWCASES) and all(state == "verified" for _, state, _ in results):
        print("\n4 / 4 SHOWCASES READY")
        print("These reports are verified and published to the persistent showcase store.")
        print("They survive replacing the Bill_XRay application folder and open instantly on Page 1.")
        return 0

    print("\nEvery curated exhibit was attempted independently. Held exhibits remain unpublished.")
    print("Nothing was force-published.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

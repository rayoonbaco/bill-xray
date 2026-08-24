from __future__ import annotations

import json
from pathlib import Path

from engine import meaning, semantic_roles, so_what

ROOT = Path(__file__).resolve().parents[1]
BILL_ID = "tcja"
ANCHOR_ID = "bxr-tcja-L3135-L3320-6e3ca5287ec6db1f"


def main() -> int:
    path = ROOT / "data" / "money" / f"{BILL_ID}.json"
    if not path.exists():
        print(f"RED FLAG: missing canonical money artifact: {path}")
        return 2
    payload = json.loads(path.read_text(encoding="utf-8"))
    finding = next((x for x in payload.get("findings", []) if x.get("anchor_id") == ANCHOR_ID), None)
    if not finding:
        print(f"RED FLAG: TCJA anchor not found in money artifact: {ANCHOR_ID}")
        return 3

    amount = next((x for x in finding.get("amounts", []) if isinstance(x, dict) and x.get("raw") == "$25,000,000"), None)
    packet = meaning.from_money(finding)
    roles = semantic_roles.resolve_money(finding, packet)
    public_text = so_what.money_explanation(finding)[0]

    print("============================================================")
    print(" BILL X-RAY - PASS 32.1.1 NUMERIC TRUNCATION TRACE")
    print("============================================================")
    print(f"Bill: {BILL_ID}")
    print(f"Anchor: {ANCHOR_ID}")
    print()
    print("1. Canonical extracted amount:")
    print(f"   {(amount or {}).get('raw') or 'MISSING'}")
    print("2. Canonical amount clause:")
    print(f"   {(amount or {}).get('context_excerpt') or 'MISSING'}")
    print("3. Meaning packet purpose after bounded role extraction:")
    print(f"   {getattr(packet, 'purpose', None) or 'MISSING'}")
    print("4. Resolved semantic purpose:")
    print(f"   {roles.purpose or 'MISSING'}")
    print("5. Regenerated public money wording:")
    print(f"   {public_text or 'MISSING'}")
    print()

    joined = " ".join(str(x or "") for x in (getattr(packet, "purpose", None), roles.purpose, public_text))
    if "$2…" in joined or "$2..." in joined:
        print("RED FLAG: partial money token still exists. Pass 32.1.1 did NOT repair the earliest boundary.")
        return 1
    if "$25,000,000" not in (public_text or ""):
        print("RED FLAG: public wording lost the canonical $25,000,000 amount.")
        return 1
    print("CLEAR: canonical $25,000,000 remains intact and no synthetic $2 truncation is present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

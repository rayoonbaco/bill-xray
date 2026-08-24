from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import audit  # noqa: E402
from engine.citations import resolve_anchor  # noqa: E402




def _held_build_root() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else (Path.home() / "AppData" / "Local")
    return base / "Bill_XRay" / "held_builds"


def _restore_durable_bundle(bill_id: str) -> bool:
    hold = _held_build_root() / bill_id
    manifest = hold / "manifest.json"
    if not manifest.exists():
        return False
    restored = 0
    for src in hold.rglob("*"):
        if not src.is_file() or src.name == "manifest.json":
            continue
        rel = src.relative_to(hold)
        dst = ROOT / "data" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        restored += 1
    if restored:
        print(f"[RESTORE] recovered {restored} held-build forensic artifact(s) from {hold}")
    return restored > 0


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _clip(value: object, limit: int = 1200) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _find_claim(analysis: dict, panel_key: str | None, anchor_id: str | None) -> dict:
    for panel in analysis.get("panels", []):
        if panel_key and str(panel.get("key") or "") != panel_key:
            continue
        for claim in panel.get("claims", []):
            citations = claim.get("citations") or []
            if anchor_id and any(str(c.get("anchor_id") or "") == anchor_id for c in citations):
                return claim
    return {}


def _origin(code: str) -> str:
    return {
        "PUBLIC_TEXT_NOT_REPRODUCIBLE": "synthesis/upstream text provenance",
        "UPSTREAM_PROVENANCE_MISSING": "missing upstream artifact or routing provenance",
        "SEMANTIC_PROVENANCE_DRIFT": "semantic-role provenance wiring",
        "NOVEL_NUMBER": "numeric fidelity / factual wording",
        "CITATION_METADATA_DRIFT": "citation metadata wiring",
        "CITATION_URL_DRIFT": "citation URL wiring",
        "ANCHOR_RESOLUTION_FAILED": "citation anchor resolution",
        "CITATION_CARDINALITY": "citation cardinality",
        "MISSING_ANCHOR": "citation anchor creation",
    }.get(code, "citation-audit provenance")


def inspect_bill(bill_id: str) -> int:
    report_path = audit.AUDIT_DIR / f"{bill_id}.json"
    analysis_path = audit.ANALYSIS_DIR / f"{bill_id}.json"
    report = _load(report_path)
    analysis = _load(analysis_path)
    if not report and _restore_durable_bundle(bill_id):
        report = _load(report_path)
        analysis = _load(analysis_path)
    if not report:
        print(f"{bill_id}: no citation-audit artifact found at {report_path}")
        print(f"Durable held-build bundle also not found at {_held_build_root() / bill_id}")
        return 2

    print("=" * 72)
    print(" BILL X-RAY - PASS 31.6.2 FRESH-BILL CITATION AUDIT FORENSICS")
    print("=" * 72)
    print(f"Bill: {bill_id}")
    print(f"Audit status: {report.get('status')} | critical={report.get('critical_count', 0)} | warnings={report.get('warning_count', 0)}")
    print(f"Citations reverified: {report.get('citations_checked', 0)}/{report.get('public_claim_count', 0)}")

    findings = report.get("findings", [])
    if not findings:
        print("No audit findings recorded.")
        return 0

    criticals = [f for f in findings if f.get("severity") == "critical"]
    warnings = [f for f in findings if f.get("severity") != "critical"]
    ordered = criticals + warnings

    indexes = {
        "translations": audit._index(audit.TRANSLATION_DIR, bill_id, "translations"),
        "money": audit._index(audit.MONEY_DIR, bill_id, "findings"),
        "power": audit._index(audit.POWER_DIR, bill_id, "findings"),
        "barrel": audit._index(audit.BARREL_DIR, bill_id, "candidates"),
        "left": audit._index(audit.LEFT_DIR, bill_id, "candidates"),
        "right": audit._index(audit.RIGHT_DIR, bill_id, "candidates"),
    }

    for idx, finding in enumerate(ordered, 1):
        panel = str(finding.get("panel") or "") or None
        anchor_id = str(finding.get("anchor_id") or "") or None
        code = str(finding.get("code") or "UNKNOWN")
        claim = _find_claim(analysis, panel, anchor_id)
        print("\n" + "-" * 72)
        print(f"FINDING {idx}: [{str(finding.get('severity') or '').upper()}] {code}")
        print(f"Likely origin: {_origin(code)}")
        print(f"Panel: {panel or 'n/a'}")
        print(f"Anchor: {anchor_id or 'n/a'}")
        print(f"Gate message: {finding.get('message')}")
        if claim:
            print(f"Published claim: {_clip(claim.get('text'))}")
            print(f"Claim class: {claim.get('claim_class')} | lens={claim.get('lens') or 'n/a'}")
        if anchor_id:
            try:
                resolved = resolve_anchor(bill_id, anchor_id)
                print(f"Canonical section: {resolved.get('section_label')}")
                print(f"Canonical location: {resolved.get('location_marker')}")
                print(f"Exact anchored source: {_clip(resolved.get('exact_text'), 1800)}")
            except Exception as exc:
                print(f"Exact anchored source: UNAVAILABLE ({exc})")

        if claim and anchor_id:
            expected_text = audit._upstream_expected(panel or "", claim, anchor_id, indexes)
            if expected_text is not None:
                print(f"Regenerated upstream wording: {_clip(expected_text, 1400)}")
            public_sem = audit._semantic_public_fields(claim)
            expected_sem = audit._semantic_expected(panel or "", anchor_id, indexes, claim)
            if public_sem or expected_sem:
                print("Semantic provenance:")
                for key in sorted(set(public_sem) | set(expected_sem)):
                    print(f"  {key}: public={public_sem.get(key)!r} | canonical={expected_sem.get(key)!r}")
            if code == "NOVEL_NUMBER":
                try:
                    resolved = resolve_anchor(bill_id, anchor_id)
                    print(f"Public numeric signatures: {sorted(audit._numeric_signatures(str(claim.get('text') or '')))}")
                    print(f"Source numeric signatures: {sorted(audit._numeric_signatures(str(resolved.get('exact_text') or '')))}")
                except Exception:
                    pass

    print("\n" + "=" * 72)
    print("FORENSIC RULE: diagnose the mismatch; do not weaken the citation gate.")
    print("=" * 72)
    return 1 if criticals else 0


def _most_recent_failed() -> str | None:
    candidates = []
    for path in audit.AUDIT_DIR.glob("*.json"):
        payload = _load(path)
        if payload.get("status") == "fail":
            candidates.append((path.stat().st_mtime, path.stem))
    return max(candidates)[1] if candidates else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explain exactly why a Bill X-Ray citation audit held a report.")
    parser.add_argument("bill_id", nargs="?", help="Bill ID, e.g. gpo-118hr171ih. If omitted, inspect the most recent failed audit.")
    args = parser.parse_args(argv)
    bill_id = args.bill_id or _most_recent_failed()
    if not bill_id:
        print("No failed citation-audit artifact was found.")
        return 2
    return inspect_bill(bill_id)


if __name__ == "__main__":
    raise SystemExit(main())

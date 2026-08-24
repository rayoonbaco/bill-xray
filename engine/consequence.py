"""Pass 30: consequence and anomaly synthesis across clearly separated evidence lanes."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "consequence"


def _load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {} if default is None else default


def _external_strength(external: dict) -> tuple[float, list[str]]:
    lanes = external.get("lanes", {})
    reasons, score = [], 0.0
    cbo = lanes.get("cbo", {})
    jct = lanes.get("jct", {})
    spend = lanes.get("usaspending", {})
    if cbo.get("status") == "found":
        score += 0.35; reasons.append("CBO official cost-estimate context found")
    if jct.get("status") == "found":
        score += 0.35; reasons.append("JCT official tax/revenue context found")
    if spend.get("status") == "found":
        score += 0.20; reasons.append("USAspending related award activity found")
    return min(1.0, score), reasons


def build_consequence_context(bill_id: str) -> dict:
    analysis = _load(ROOT / "data" / "analyses" / f"{bill_id}.json")
    external = _load(ROOT / "data" / "external_evidence" / f"{bill_id}.json")
    money = _load(ROOT / "data" / "money" / f"{bill_id}.json")
    barrel = _load(ROOT / "data" / "barrel_scan" / f"{bill_id}.json")

    external_score, reasons = _external_strength(external)
    direct_money = sum(1 for x in money.get("findings", []) if x.get("status") == "finding")
    high_scrutiny = sum(1 for x in barrel.get("candidates", []) if float(x.get("candidate_score", 0)) >= 0.70)
    published = sum(len(p.get("claims", [])) for p in analysis.get("panels", []))

    # This is intentionally a coverage/confidence score, not a corruption score.
    consequence_confidence = round(min(1.0, 0.35 + min(0.25, direct_money / 40.0) + min(0.20, high_scrutiny / 20.0) + external_score * 0.20), 3)
    if direct_money:
        reasons.append(f"{direct_money} source-bound fiscal findings available")
    if high_scrutiny:
        reasons.append(f"{high_scrutiny} high-scrutiny statutory candidates available")
    if not reasons:
        reasons.append("Only statutory text is available; external consequence context is limited")

    payload = {
        "schema_version": "30.0",
        "bill_id": bill_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "consequence_confidence": consequence_confidence,
        "published_claims": published,
        "signals": {"direct_money_findings": direct_money, "high_scrutiny_candidates": high_scrutiny, "external_evidence_strength": round(external_score, 3)},
        "reasons": reasons,
        "guardrail": "This score measures consequence-evidence coverage, not corruption, partisan intent, fraud, or policy quality.",
        "evidence_lanes": {
            "statute": "What Congress legally wrote",
            "cbo_jct": "Expected fiscal consequence where official estimates are available",
            "usaspending": "Related implementation spending activity; not causal attribution",
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{bill_id}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def consequence_status(bill_id: str) -> dict:
    return _load(OUT_DIR / f"{bill_id}.json", {"bill_id": bill_id, "status": "not_generated"})

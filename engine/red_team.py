"""Pass 18: political-bias and selection-quality red team for Bill X-Ray.

The red team audits the *published five-panel selection*, not the politics of the bill.
It looks for asymmetric advocacy treatment, evidence misalignment, trivial-dollar
selection, weak Barrel Scan rationales, source-like legalese, and concentration on a
small number of anchors. It can fail a report even when every individual claim is cited.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from engine import fiscal_materiality

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = ROOT / "data" / "analyses"
MONEY_DIR = ROOT / "data" / "money"
BARREL_DIR = ROOT / "data" / "barrel_scan"
RED_TEAM_DIR = ROOT / "data" / "red_team"
PROVING_GROUND_BILLS = ("aca", "obbba")
RED_TEAM_VERSION = "30.1-fiscal-object-provenance"


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    panel: str | None = None
    anchor_id: str | None = None


@dataclass(frozen=True)
class RedTeamReport:
    schema_version: str
    red_team_version: str
    bill_id: str
    status: str
    score: float
    critical_count: int
    warning_count: int
    findings: list[Finding]
    checks: dict


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _panel_map(analysis: dict) -> dict[str, dict]:
    return {p.get("key"): p for p in analysis.get("panels", [])}


def _anchor(claim: dict) -> str | None:
    cites = claim.get("citations") or []
    return str(cites[0].get("anchor_id")) if cites and cites[0].get("anchor_id") else None


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def _money_materiality(payload: dict) -> dict[str, fiscal_materiality.FiscalMateriality]:
    out: dict[str, fiscal_materiality.FiscalMateriality] = {}
    for item in payload.get("findings", []):
        aid = item.get("anchor_id")
        if not aid:
            continue
        assessment = fiscal_materiality.assess(item)
        if assessment.actionable:
            out[str(aid)] = assessment
    return out

def _barrel_index(payload: dict) -> dict[str, dict]:
    return {str(x["anchor_id"]): x for x in payload.get("candidates", []) if x.get("anchor_id")}


def audit_analysis(bill_id: str, *, write: bool = True) -> RedTeamReport:
    analysis_path = ANALYSIS_DIR / f"{bill_id}.json"
    if not analysis_path.exists():
        raise FileNotFoundError(f"Public analysis not found: {analysis_path}")
    analysis = _load(analysis_path)
    panels = _panel_map(analysis)
    findings: list[Finding] = []

    # 1. Citation / anchor integrity on every published claim.
    all_claims = [(key, claim) for key, panel in panels.items() for claim in panel.get("claims", [])]
    for key, claim in all_claims:
        aid = _anchor(claim)
        if not aid:
            findings.append(Finding("critical", "MISSING_ANCHOR", "A public claim has no stable citation anchor.", key, None))

    # 2. LEFT | RIGHT | TEXT must compare the same statutory proposition.
    lens_claims = panels.get("left_right_text", {}).get("claims", [])
    lens_by = {c.get("lens"): c for c in lens_claims}
    if set(lens_by) != {"LEFT", "RIGHT", "TEXT"}:
        findings.append(Finding("critical", "LENS_SURFACE_INCOMPLETE", "LEFT | RIGHT | TEXT is incomplete.", "left_right_text"))
    else:
        anchors = {_anchor(lens_by[l]) for l in ("LEFT", "RIGHT", "TEXT")}
        if len(anchors) != 1:
            findings.append(Finding("critical", "LENS_ANCHOR_MISMATCH", "LEFT, RIGHT, and TEXT are not grounded in the same statutory anchor.", "left_right_text"))
        left_words = _word_count(lens_by["LEFT"].get("text", ""))
        right_words = _word_count(lens_by["RIGHT"].get("text", ""))
        ratio = (left_words / right_words) if right_words else 99.0
        if ratio < 0.60 or ratio > 1.67:
            findings.append(Finding("warning", "LENS_LENGTH_ASYMMETRY", "One advocacy lane is materially more developed than the other.", "left_right_text", _anchor(lens_by["LEFT"])))
        for lens in ("LEFT", "RIGHT"):
            if lens_by[lens].get("claim_class") not in {"INTERPRETATION", "DISPUTED"}:
                findings.append(Finding("critical", "ADVOCACY_FACT_LEAK", f"{lens} advocacy escaped its interpretation classification.", "left_right_text", _anchor(lens_by[lens])))

    # 3. Kitchen-table language check. Citation-safe legalese can still be poor public output.
    legal_markers = ("read as follows", "<note", "subsection (", "paragraph (", "qualified opportunity zone business--")
    for key, claim in all_claims:
        if key == "left_right_text" and claim.get("lens") in {"LEFT", "RIGHT"}:
            continue
        text = str(claim.get("text", ""))
        if len(text) > 360 or any(marker in text.lower() for marker in legal_markers):
            findings.append(Finding("warning", "PUBLIC_LEGALESE", "A front-page claim is still too close to source-code legal language for the Kitchen Table Test.", key, _anchor(claim)))

    # 4. Money selection should prefer consequential statutory amounts over token figures.
    money_payload = _load(MONEY_DIR / f"{bill_id}.json")
    materiality_by_anchor = _money_materiality(money_payload)
    money_claims = panels.get("follow_the_money", {}).get("claims", [])
    selected_ids = {_anchor(c) for c in money_claims if _anchor(c)}

    # Compare like with like. A giant contextual projection or a different fiscal
    # mechanic must not automatically invalidate a smaller operative provision.
    available_by_bucket: dict[str, list[fiscal_materiality.FiscalMateriality]] = {}
    selected_by_bucket: dict[str, list[fiscal_materiality.FiscalMateriality]] = {}
    for aid, item in materiality_by_anchor.items():
        available_by_bucket.setdefault(item.bucket, []).append(item)
        if aid in selected_ids:
            selected_by_bucket.setdefault(item.bucket, []).append(item)

    raw_money_by_anchor = {str(x.get("anchor_id")): x for x in money_payload.get("findings", []) if x.get("anchor_id")}

    def _fmt_money(aid: str, assessment: fiscal_materiality.FiscalMateriality) -> str:
        raw = raw_money_by_anchor.get(aid, {})
        section = str(raw.get("section_label") or raw.get("section") or aid)
        return (
            f"anchor={aid}; section={section}; amount=${assessment.amount:,.0f}; "
            f"class={assessment.bucket}; directness={assessment.directness:.2f}; score={assessment.score:.3f}; "
            f"provenance={assessment.provenance}; context_kind={assessment.context_kind}; "
            f"context={assessment.source_context[:180]!r}"
        )

    material_omissions: list[tuple[str, str | None, fiscal_materiality.FiscalMateriality | None, str, fiscal_materiality.FiscalMateriality, float]] = []
    for bucket, available in available_by_bucket.items():
        top_aid, top_available_item = max(
            ((aid, item) for aid, item in materiality_by_anchor.items() if item.bucket == bucket),
            key=lambda row: (row[1].amount, row[1].score),
        )
        selected_pairs = [(aid, materiality_by_anchor[aid]) for aid in selected_ids if aid in materiality_by_anchor and materiality_by_anchor[aid].bucket == bucket]
        if top_available_item.amount < 100_000_000:
            continue
        if not selected_pairs:
            selected_scores = [x.score for vals in selected_by_bucket.values() for x in vals]
            if top_available_item.directness >= 0.90 and top_available_item.score > max(selected_scores, default=0.0) * 1.35:
                material_omissions.append((bucket, None, None, top_aid, top_available_item, float("inf")))
            continue
        selected_aid, selected_item = max(selected_pairs, key=lambda row: (row[1].amount, row[1].score))
        ratio = top_available_item.amount / max(selected_item.amount, 1.0)
        if selected_item.amount < top_available_item.amount * 0.10:
            material_omissions.append((bucket, selected_aid, selected_item, top_aid, top_available_item, ratio))

    for bucket, selected_aid, selected_item, omitted_aid, omitted_item, ratio in material_omissions:
        selected_desc = "none selected in this class" if selected_item is None or selected_aid is None else _fmt_money(selected_aid, selected_item)
        omitted_desc = _fmt_money(omitted_aid, omitted_item)
        ratio_text = "n/a" if ratio == float("inf") else f"{ratio:.1f}x"
        message = (
            "Follow the Money omitted a materially larger actionable fiscal provision within a comparable fiscal class. "
            f"PUBLISHED: {selected_desc}. OMITTED LARGER: {omitted_desc}. RATIO={ratio_text}. "
            "This diagnostic is intentionally explicit so selection/classification can be inspected without weakening the gate."
        )
        findings.append(Finding("critical", "MONEY_SELECTION_TRIVIALIZED", message, "follow_the_money", omitted_aid))

    selected_material = [materiality_by_anchor[aid] for aid in selected_ids if aid in materiality_by_anchor]
    selected_amounts = [x.amount for x in selected_material]
    actionable_amounts = [x.amount for x in materiality_by_anchor.values()]
    if selected_amounts and max(selected_amounts) < 1_000_000 and max(actionable_amounts, default=0.0) >= 1_000_000:
        findings.append(Finding("warning", "MONEY_DE_MINIMIS", "Follow the Money is dominated by small actionable fiscal figures despite larger comparable provisions in the bill.", "follow_the_money"))

    # 5. Barrel Scan needs a real independent scrutiny signal, not lexical distance alone.
    barrel_payload = _load(BARREL_DIR / f"{bill_id}.json")
    barrel_by_anchor = _barrel_index(barrel_payload)
    for claim in panels.get("barrel_scan", {}).get("claims", []):
        aid = _anchor(claim)
        raw = barrel_by_anchor.get(aid or "", {})
        factors = raw.get("factors") or {}
        independent = max(
            float(factors.get("beneficiary_concentration", 0.0)),
            float(factors.get("fiscal_significance", 0.0)),
            float(factors.get("scope_surprise", 0.0)),
            float(factors.get("cross_reference_opacity", 0.0)),
            float(factors.get("narrow_carve_out", 0.0)),
        )
        reason = str(claim.get("why_flagged") or claim.get("text") or "").lower()
        if independent < 0.35 or "lexically distant" in reason and independent < 0.50:
            findings.append(Finding("critical", "BARREL_WEAK_SIGNAL", "A public Barrel Scan flag relies too heavily on lexical topical distance without a strong independent scrutiny signal.", "barrel_scan", aid))

    # 6. Detect evidence concentration / repetitive selection.
    anchors = [_anchor(c) for _, c in all_claims if _anchor(c)]
    if anchors:
        most = max(anchors.count(a) for a in set(anchors))
        if most >= 6:
            findings.append(Finding("warning", "ANCHOR_CONCENTRATION", "Too much of the public report is carried by one statutory anchor.", None))

    # 7. Political vocabulary should be isolated to the explicit advocacy lanes.
    partisan_words = re.compile(r"\b(progressive|conservative|left|right|liberal|republican|democrat(?:ic)?)\b", re.I)
    for key, claim in all_claims:
        if key == "left_right_text" and claim.get("lens") in {"LEFT", "RIGHT"}:
            continue
        if partisan_words.search(str(claim.get("text", ""))):
            findings.append(Finding("critical", "POLITICAL_LANGUAGE_LEAK", "Political framing leaked outside the labeled advocacy lanes.", key, _anchor(claim)))

    critical = sum(f.severity == "critical" for f in findings)
    warnings = sum(f.severity == "warning" for f in findings)
    score = max(0.0, round(1.0 - 0.18 * critical - 0.05 * warnings, 3))
    status = "fail" if critical else ("pass_with_warnings" if warnings else "pass")
    checks = {
        "same_anchor_left_right_text": not any(f.code == "LENS_ANCHOR_MISMATCH" for f in findings),
        "advocacy_classification_intact": not any(f.code == "ADVOCACY_FACT_LEAK" for f in findings),
        "money_selection_material": not any(f.code in {"MONEY_SELECTION_TRIVIALIZED", "MONEY_DE_MINIMIS"} for f in findings),
        "barrel_independent_signal": not any(f.code == "BARREL_WEAK_SIGNAL" for f in findings),
        "political_language_contained": not any(f.code == "POLITICAL_LANGUAGE_LEAK" for f in findings),
        "kitchen_table_language": not any(f.code == "PUBLIC_LEGALESE" for f in findings),
    }
    report = RedTeamReport("18.0", RED_TEAM_VERSION, bill_id, status, score, critical, warnings, findings, checks)
    if write:
        RED_TEAM_DIR.mkdir(parents=True, exist_ok=True)
        (RED_TEAM_DIR / f"{bill_id}.json").write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def red_team_status() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for bill_id in PROVING_GROUND_BILLS:
        path = RED_TEAM_DIR / f"{bill_id}.json"
        if not path.exists():
            out[bill_id] = {"red_team_ready": False, "status": "not_run", "score": 0.0, "critical_count": 0, "warning_count": 0}
            continue
        p = _load(path)
        out[bill_id] = {
            "red_team_ready": p.get("status") in {"pass", "pass_with_warnings"},
            "status": p.get("status", "fail"),
            "score": p.get("score", 0.0),
            "critical_count": p.get("critical_count", 0),
            "warning_count": p.get("warning_count", 0),
            "checks": p.get("checks", {}),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Pass 18 political-bias and selection-quality red team.")
    parser.add_argument("bill_ids", nargs="*", default=list(PROVING_GROUND_BILLS))
    args = parser.parse_args(argv)
    failed = False
    for bill_id in args.bill_ids:
        try:
            report = audit_analysis(bill_id)
            print(f"{bill_id}: {report.status}; score={report.score:.3f}; critical={report.critical_count}; warnings={report.warning_count}")
            failed = failed or report.status == "fail"
        except Exception as exc:
            failed = True
            print(f"{bill_id}: ERROR - {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

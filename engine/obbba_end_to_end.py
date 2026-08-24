"""Pass 17: OBBBA end-to-end proving-ground runner.

Runs the complete evidence spine against official Public Law 119-21 text acquired
from GovInfo. Advocacy frames are explicitly curated, source-bound interpretations;
they never modify the statutory evidence or TEXT lane.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine import ingest, segment, citations, translator, money, power, barrel_scan, topic_expert
from engine import left_lens, right_lens, skeptic, referee, synthesis, red_team, audit, challenge, external_evidence, consequence
from engine.progress import StageTracker

ROOT = Path(__file__).resolve().parents[1]
STATUS_DIR = ROOT / "data" / "end_to_end"

CURATED_FRAMES = [
    {
        "match": ["SEC. 70201"],
        "left": "A progressive reading emphasizes that the qualified-tips deduction delivers targeted tax relief but is limited by eligibility rules, a dollar cap, and income-based phaseouts written into the provision.",
        "right": "A conservative reading emphasizes reducing taxable income for workers who receive qualified tips while using explicit caps and income limits to bound the deduction.",
    },
    {
        "match": ["SEC. 71119"],
        "left": "A progressive reading emphasizes that Medicaid coverage for certain adults becomes conditional on satisfying and documenting community-engagement requirements, creating an additional eligibility hurdle.",
        "right": "A conservative reading emphasizes conditioning Medicaid eligibility for certain adults on work or other qualifying community engagement and requiring states to verify compliance.",
    },
    {
        "match": ["SEC. 71301", "SEC. 71303"],
        "left": "A progressive reading emphasizes that tighter premium-tax-credit eligibility and verification rules can narrow or complicate access to federal assistance for some people seeking marketplace coverage.",
        "right": "A conservative reading emphasizes narrowing premium-tax-credit eligibility and strengthening verification so federal subsidies are limited to people who satisfy the statutory requirements.",
    },
]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def author_advocacy(bill_id: str = "obbba") -> int:
    lp = ROOT / "data" / "left_lens" / f"{bill_id}.json"
    rp = ROOT / "data" / "right_lens" / f"{bill_id}.json"
    left = _load(lp)
    right = _load(rp)
    right_by = {x["anchor_id"]: x for x in right.get("candidates", [])}
    authored = 0
    for item in left.get("candidates", []):
        label = str(item.get("section_label", "")).upper()
        frame = next((f for f in CURATED_FRAMES if any(m in label for m in f["match"])), None)
        peer = right_by.get(item.get("anchor_id"))
        if not frame or not peer:
            continue
        item["public_interpretation"] = frame["left"]
        peer["public_interpretation"] = frame["right"]
        provenance = "Pass 17 curated proving-ground interpretation; classification remains INTERPRETATION"
        item["public_interpretation_provenance"] = provenance
        peer["public_interpretation_provenance"] = provenance
        authored += 1
    _write(lp, left)
    _write(rp, right)
    return authored


def run_obbba() -> dict:
    source = ingest.SOURCE_DIR / "obbba.txt"
    if not source.exists():
        raise FileNotFoundError("Official OBBBA local source is missing. Run tools/fetch_obbba_source.py first.")

    tracker = StageTracker("obbba", STATUS_DIR, 19)
    ing = tracker.run("ingest", "Ingest official Public Law 119-21 text", lambda: ingest.ingest_manifest_bill("obbba"), lambda x: f"{x.line_count:,} lines")
    seg = tracker.run("segment", "Segment titles, subtitles, chapters, and sections", lambda: segment.segment_ingested_bill("obbba"), lambda x: f"{x.segment_count:,} structural blocks")
    anc = tracker.run("anchors", "Build exact citation anchors", lambda: citations.build_anchor_index("obbba"), lambda x: f"{len(x.anchors):,} anchors")
    trans = tracker.run("translate", "Run plain-English translator", lambda: translator.translate_bill("obbba"), lambda x: f"{len(x.translations):,} translation packets")
    mon = tracker.run("money", "Extract money mechanics", lambda: money.extract_bill("obbba"), lambda x: f"{len(x.findings):,} findings")
    pwr = tracker.run("power", "Extract power and authority mechanics", lambda: power.extract_bill("obbba"), lambda x: f"{len(x.findings):,} findings")
    bar = tracker.run("barrel", "Run Barrel Scan candidate detector", lambda: barrel_scan.scan_bill("obbba"), lambda x: f"{len(x.candidates):,} candidates")
    top = tracker.run("topics", "Route provisions to dynamic topic experts", lambda: topic_expert.review_bill("obbba"), lambda x: f"{len(x.reviews):,} reviews")
    tracker.run("left", "Build Left Lens packets", lambda: left_lens.build_left_lens("obbba"), lambda x: f"{len(x.candidates):,} candidates")
    tracker.run("right", "Build Right Lens packets", lambda: right_lens.build_right_lens("obbba"), lambda x: f"{len(x.candidates):,} candidates")
    authored = tracker.run("advocacy", "Attach source-bound proving-ground interpretations", lambda: author_advocacy("obbba"), lambda x: f"{x:,} matched pairs")
    sk = tracker.run("skeptic", "Run Investigative Skeptic", lambda: skeptic.build_skeptic_review("obbba"), lambda x: f"{len(x.packets):,} packets")
    ref = tracker.run("referee", "Run Neutral Referee", lambda: referee.build_referee_review("obbba"), lambda x: f"{len(x.decisions):,} decisions")
    syn = tracker.run("synthesis", "Build five-panel synthesis", lambda: synthesis.synthesize_bill("obbba"), lambda x: f"{x.selected_count:,} public claims; {x.analysis_status}")
    lens_diag = synthesis.diagnose_lens_surface("obbba")
    print(
        f"      LEFT | RIGHT | TEXT diagnostics: authored={lens_diag['authored_pair_count']}; "
        f"complete_same-anchor={lens_diag['complete_anchor_count']}",
        flush=True,
    )
    if lens_diag["complete_anchor_count"] == 0:
        for row in lens_diag["anchors"][:8]:
            reasons = ", ".join(row["reasons"]) or "none"
            print(
                f"        anchor={row['anchor_id']} section={row['section_label']} "
                f"referee={row['referee_status']} translation={row['translation_status']} text_referee={row.get('text_referee_status','?')} reasons={reasons}",
                flush=True,
            )
    ext = tracker.run("external", "Pull official external evidence", lambda: external_evidence.collect_external_evidence("obbba"), lambda x: f"CBO={x['lanes']['cbo']['status']}; JCT={x['lanes']['jct']['status']}; USAspending={x['lanes']['usaspending']['status']}")
    con = tracker.run("consequence", "Build consequence evidence context", lambda: consequence.build_consequence_context("obbba"), lambda x: f"coverage confidence {x['consequence_confidence']:.3f}")
    red = tracker.run("red_team", "Run political-bias and selection-quality red team", lambda: red_team.audit_analysis("obbba"), lambda x: f"{x.status}; score {x.score:.3f}")
    if red.findings:
        print("      red-team findings:", flush=True)
        for finding in red.findings:
            where = f" panel={finding.panel}" if finding.panel else ""
            anchor = f" anchor={finding.anchor_id}" if finding.anchor_id else ""
            print(f"        [{finding.severity.upper()}] {finding.code}{where}{anchor}: {finding.message}", flush=True)
    else:
        print("      red-team findings: none", flush=True)
    aud = tracker.run("audit", "Run hallucination and citation audit", lambda: audit.audit_bill("obbba"), lambda x: f"{x.status}; {x.citations_checked}/{x.public_claim_count} citations reverified")
    if aud.findings:
        print("      citation audit findings:", flush=True)
        for finding in aud.findings:
            where = f" panel={finding.panel}" if finding.panel else ""
            anchor = f" anchor={finding.anchor_id}" if finding.anchor_id else ""
            print(f"        [{finding.severity.upper()}] {finding.code}{where}{anchor}: {finding.message}", flush=True)
    else:
        print("      citation audit findings: none", flush=True)
    chal = tracker.run("challenge", "Run hostile context and comprehension challenge", lambda: challenge.audit_analysis("obbba"), lambda x: f"{x.status}; score {x.score:.3f}")
    if chal.findings:
        print("      hostile-challenge findings:", flush=True)
        for finding in chal.findings:
            where = f" panel={finding.panel}" if finding.panel else ""
            anchor = f" anchor={finding.anchor_id}" if finding.anchor_id else ""
            print(f"        [{finding.severity}] {finding.code}{where}{anchor}: {finding.message}", flush=True)
    else:
        print("      hostile-challenge findings: none", flush=True)
    release_ok = syn.analysis_status == "verified" and red.status != "fail" and aud.status != "fail" and chal.status != "fail"
    progress = tracker.finish("complete" if release_ok else "release_hold")

    result = {
        "schema_version": "19.3",
        "bill_id": "obbba",
        "source_sha256": ing.sha256,
        "source_bytes": ing.byte_count,
        "source_lines": ing.line_count,
        "segments": seg.segment_count,
        "anchors": len(anc.anchors),
        "translations": len(trans.translations),
        "money_findings": len(mon.findings),
        "power_findings": len(pwr.findings),
        "barrel_candidates": len(bar.candidates),
        "topic_reviews": len(top.reviews),
        "advocacy_pairs_authored": authored,
        "skeptic_packets": len(sk.packets),
        "referee_decisions": len(ref.decisions),
        "analysis_status": syn.analysis_status,
        "public_claims": syn.selected_count,
        "red_team_status": red.status,
        "red_team_score": red.score,
        "red_team_critical_count": red.critical_count,
        "red_team_warning_count": red.warning_count,
        "citation_audit_status": aud.status,
        "challenge_status": chal.status,
        "challenge_score": chal.score,
        "external_evidence": {k: v.get("status") for k, v in ext.get("lanes", {}).items()},
        "consequence_confidence": con.get("consequence_confidence"),
        "challenge_blocker_count": chal.blocker_count,
        "challenge_important_count": chal.important_count,
        "citation_audit_critical_count": aud.critical_count,
        "citation_audit_warning_count": aud.warning_count,
        "citations_reverified": aud.citations_checked,
        "public_claims_reproduced": aud.upstream_claims_reproduced,
        "missing_public_lanes": syn.missing_public_lanes,
        "lens_authored_pair_count": lens_diag["authored_pair_count"],
        "lens_complete_anchor_count": lens_diag["complete_anchor_count"],
        "lens_complete_anchor_ids": lens_diag["complete_anchor_ids"],
        "elapsed_seconds": progress["elapsed_seconds"],
        "stage_timings": {r["key"]: r["elapsed_seconds"] for r in progress["stages"]},
        "source_scope_note": "Analyzes Public Law 119-21 as enacted on July 4, 2025; later amendments, regulations, litigation, implementation, and external fiscal estimates require separate authoritative context.",
    }
    _write(STATUS_DIR / "obbba.json", result)
    return result


def obbba_status() -> dict:
    path = STATUS_DIR / "obbba.json"
    progress_path = STATUS_DIR / "obbba_progress.json"
    progress = _load(progress_path) if progress_path.exists() else None
    if not path.exists():
        return {"obbba": {"end_to_end_ready": False, "analysis_status": "not_run", "progress": progress}}
    payload = _load(path)
    return {"obbba": {"end_to_end_ready": payload.get("analysis_status") == "verified", **payload, "progress": progress}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    result = run_obbba()
    print("\nPASS 17 OBBBA RESULT", flush=True)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result["analysis_status"] == "verified" and result.get("red_team_status") != "fail" and result.get("citation_audit_status") != "fail" else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Pass 16: ACA end-to-end proving-ground runner, hardened in Pass 17.

Runs the complete evidence spine against the official local ACA text. Pass 17 adds
visible stage progress, timings, and durable checkpoints so a real-bill run never
looks frozen while it is working.
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
        "match": ["SEC. 1201", "SEC. 1001"],
        "left": "A progressive reading emphasizes nationwide consumer protections against insurance practices that can make coverage unavailable or less meaningful when people become sick.",
        "right": "A conservative reading emphasizes that nationwide insurance rules can reduce insurer and state flexibility over benefit design, underwriting, and market regulation.",
    },
    {
        "match": ["SEC. 1311", "SEC. 1321"],
        "left": "A progressive reading emphasizes organized insurance marketplaces and public rules intended to make plan comparison and access easier for consumers.",
        "right": "A conservative reading emphasizes the expansion of federal and state administrative machinery needed to define, supervise, and operate regulated insurance marketplaces.",
    },
    {
        "match": ["SEC. 1401"],
        "left": "A progressive reading emphasizes federal premium assistance as a way to make regulated private insurance more affordable for eligible households.",
        "right": "A conservative reading emphasizes that premium tax credits commit federal resources and tie assistance to a federally structured insurance-market framework.",
    },
]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def author_advocacy(bill_id: str = "aca") -> int:
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
        provenance = "Pass 16 curated proving-ground interpretation; classification remains INTERPRETATION"
        item["public_interpretation_provenance"] = provenance
        peer["public_interpretation_provenance"] = provenance
        authored += 1
    _write(lp, left)
    _write(rp, right)
    return authored


def run_aca() -> dict:
    source = ingest.SOURCE_DIR / "aca.txt"
    if not source.exists():
        raise FileNotFoundError("Official ACA local source is missing. Run tools/fetch_aca_source.py first.")

    tracker = StageTracker("aca", STATUS_DIR, 19)
    ing = tracker.run("ingest", "Ingest official Public Law 111-148 text", lambda: ingest.ingest_manifest_bill("aca"), lambda x: f"{x.line_count:,} lines")
    seg = tracker.run("segment", "Segment titles, subtitles, chapters, and sections", lambda: segment.segment_ingested_bill("aca"), lambda x: f"{x.segment_count:,} structural blocks")
    anc = tracker.run("anchors", "Build exact citation anchors", lambda: citations.build_anchor_index("aca"), lambda x: f"{len(x.anchors):,} anchors")
    trans = tracker.run("translate", "Run plain-English translator", lambda: translator.translate_bill("aca"), lambda x: f"{len(x.translations):,} translation packets")
    mon = tracker.run("money", "Extract money mechanics", lambda: money.extract_bill("aca"), lambda x: f"{len(x.findings):,} findings")
    pwr = tracker.run("power", "Extract power and authority mechanics", lambda: power.extract_bill("aca"), lambda x: f"{len(x.findings):,} findings")
    bar = tracker.run("barrel", "Run Barrel Scan candidate detector", lambda: barrel_scan.scan_bill("aca"), lambda x: f"{len(x.candidates):,} candidates")
    top = tracker.run("topics", "Route provisions to dynamic topic experts", lambda: topic_expert.review_bill("aca"), lambda x: f"{len(x.reviews):,} reviews")
    tracker.run("left", "Build Left Lens packets", lambda: left_lens.build_left_lens("aca"), lambda x: f"{len(x.candidates):,} candidates")
    tracker.run("right", "Build Right Lens packets", lambda: right_lens.build_right_lens("aca"), lambda x: f"{len(x.candidates):,} candidates")
    authored = tracker.run("advocacy", "Attach source-bound proving-ground interpretations", lambda: author_advocacy("aca"), lambda x: f"{x:,} matched pairs")
    sk = tracker.run("skeptic", "Run Investigative Skeptic", lambda: skeptic.build_skeptic_review("aca"), lambda x: f"{len(x.packets):,} packets")
    ref = tracker.run("referee", "Run Neutral Referee", lambda: referee.build_referee_review("aca"), lambda x: f"{len(x.decisions):,} decisions")
    syn = tracker.run("synthesis", "Build five-panel synthesis", lambda: synthesis.synthesize_bill("aca"), lambda x: f"{x.selected_count:,} public claims; {x.analysis_status}")
    lens_diag = synthesis.diagnose_lens_surface("aca")
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
    ext = tracker.run("external", "Pull official external evidence", lambda: external_evidence.collect_external_evidence("aca"), lambda x: f"CBO={x['lanes']['cbo']['status']}; JCT={x['lanes']['jct']['status']}; USAspending={x['lanes']['usaspending']['status']}")
    con = tracker.run("consequence", "Build consequence evidence context", lambda: consequence.build_consequence_context("aca"), lambda x: f"coverage confidence {x['consequence_confidence']:.3f}")
    red = tracker.run("red_team", "Run political-bias and selection-quality red team", lambda: red_team.audit_analysis("aca"), lambda x: f"{x.status}; score {x.score:.3f}")
    if red.findings:
        print("      red-team findings:", flush=True)
        for finding in red.findings:
            where = f" panel={finding.panel}" if finding.panel else ""
            anchor = f" anchor={finding.anchor_id}" if finding.anchor_id else ""
            print(f"        [{finding.severity.upper()}] {finding.code}{where}{anchor}: {finding.message}", flush=True)
    else:
        print("      red-team findings: none", flush=True)
    aud = tracker.run("audit", "Run hallucination and citation audit", lambda: audit.audit_bill("aca"), lambda x: f"{x.status}; {x.citations_checked}/{x.public_claim_count} citations reverified")
    if aud.findings:
        print("      citation audit findings:", flush=True)
        for finding in aud.findings:
            where = f" panel={finding.panel}" if finding.panel else ""
            anchor = f" anchor={finding.anchor_id}" if finding.anchor_id else ""
            print(f"        [{finding.severity.upper()}] {finding.code}{where}{anchor}: {finding.message}", flush=True)
    else:
        print("      citation audit findings: none", flush=True)
    chal = tracker.run("challenge", "Run hostile context and comprehension challenge", lambda: challenge.audit_analysis("aca"), lambda x: f"{x.status}; score {x.score:.3f}")
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
        "bill_id": "aca",
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
        "source_scope_note": "Analyzes Public Law 111-148 as enacted on March 23, 2010; later amendments, court decisions, and implementation history require separate external context.",
    }
    _write(STATUS_DIR / "aca.json", result)
    return result


def aca_status() -> dict:
    path = STATUS_DIR / "aca.json"
    progress_path = STATUS_DIR / "aca_progress.json"
    progress = _load(progress_path) if progress_path.exists() else None
    if not path.exists():
        return {"aca": {"end_to_end_ready": False, "analysis_status": "not_run", "progress": progress}}
    payload = _load(path)
    return {"aca": {"end_to_end_ready": payload.get("analysis_status") == "verified", **payload, "progress": progress}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    result = run_aca()
    print("\nPASS 16 ACA RESULT", flush=True)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result["analysis_status"] == "verified" and result.get("red_team_status") != "fail" and result.get("citation_audit_status") != "fail" else 2


if __name__ == "__main__":
    raise SystemExit(main())

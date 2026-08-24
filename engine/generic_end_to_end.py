"""Pass 22: generic 16-stage runner for a GovInfo-selected congressional bill version."""
from __future__ import annotations
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from engine import ingest, segment, citations, translator, money, power, barrel_scan, topic_expert
from engine import left_lens, right_lens, skeptic, referee, synthesis, red_team, audit, challenge, external_evidence, consequence, so_what, meaning, pass26_intelligence
from engine.progress import StageTracker
from engine.bill_search import selected_bill

ROOT = Path(__file__).resolve().parents[1]
STATUS_DIR = ROOT / "data" / "end_to_end"

LEFT_THEMES = {
    "health": "access, affordability, patient protection, and whether burdens fall fairly",
    "tax": "who receives the tax benefit or bears the burden and whether gains are broadly shared",
    "finance": "consumer protection, systemic stability, accountability, and fair access to credit",
    "defense_security": "legitimate security needs, democratic oversight, civil liberties, and public cost",
    "energy": "affordability, clean-energy transition, resilience, and distribution of public support",
    "environment": "public health, environmental safeguards, climate resilience, and frontline communities",
    "agriculture": "family farms, nutrition access, rural resilience, and concentration of benefits",
    "technology": "innovation alongside worker, consumer, privacy, competition, and public-interest protections",
    "labor": "worker bargaining power, wages, safety, benefits, and job quality",
    "infrastructure_transport": "reliable public infrastructure, jobs, access, safety, and community benefit",
    "education": "educational access, affordability, quality, and distribution of opportunity",
    "housing": "housing affordability, stability, supply, and who captures public support",
    "immigration": "due process, humane administration, family impacts, and workable legal pathways",
    "civil_liberties_justice": "due process, privacy, equal treatment, civil rights, and accountable enforcement",
    "general_legislative": "distributional fairness, public capacity, rights, and democratic accountability",
}
RIGHT_THEMES = {
    "health": "cost, market flexibility, federal reach, insurer and state discretion, and unintended incentives",
    "tax": "tax burden, incentives to work and invest, complexity, federal cost, and concentration of subsidies",
    "finance": "regulatory burden, credit availability, market competition, moral hazard, and federal discretion",
    "defense_security": "security effectiveness, executive flexibility, constitutional limits, oversight, and cost",
    "energy": "energy reliability, consumer cost, market distortion, permitting, and government-directed investment",
    "environment": "compliance cost, property and state authority, regulatory reach, and measurable environmental benefit",
    "agriculture": "producer flexibility, market incentives, program dependency, federal cost, and benefit concentration",
    "technology": "innovation incentives, regulatory burden, national competitiveness, government picking winners, and privacy",
    "labor": "employer flexibility, hiring incentives, compliance cost, worker choice, and unintended labor-market effects",
    "infrastructure_transport": "federal cost, local control, project selection, permitting, and long-run maintenance burden",
    "education": "family and local control, federal reach, institutional incentives, cost, and measurable outcomes",
    "housing": "supply incentives, taxpayer exposure, local control, subsidy effects, and market distortion",
    "immigration": "border and enforcement credibility, administrative control, incentives, public cost, and rule of law",
    "civil_liberties_justice": "constitutional limits, public safety, enforcement discretion, due process, and federal power",
    "general_legislative": "federal cost, government reach, incentives, local or private autonomy, and unintended consequences",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")




def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _held_build_root() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else (Path.home() / "AppData" / "Local")
    return base / "Bill_XRay" / "held_builds"


def _persist_failed_audit_bundle(bill_id: str, audit_report) -> Path:
    """Durably preserve a held fresh-bill audit and the evidence needed to inspect it.

    Fresh searched bills live inside the replaceable application folder.  A release-held
    audit must survive installing the next patch, so copy the audit plus its source-bound
    provenance spine into LOCALAPPDATA before the release decision returns control.
    """
    # Belt-and-suspenders local persistence: audit.audit_bill(write=True) should already
    # create this artifact, but the release boundary verifies it exists before proceeding.
    local_audit = audit.AUDIT_DIR / f"{bill_id}.json"
    _atomic_write_json(local_audit, asdict(audit_report))

    hold = _held_build_root() / bill_id
    tmp = hold.with_name(hold.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)

    rels = [
        Path("source_documents") / f"{bill_id}.txt",
        Path("ingested") / f"{bill_id}.json",
        Path("segments") / f"{bill_id}.json",
        Path("citation_anchors") / f"{bill_id}.json",
        Path("translations") / f"{bill_id}.json",
        Path("money") / f"{bill_id}.json",
        Path("power") / f"{bill_id}.json",
        Path("barrel_scan") / f"{bill_id}.json",
        Path("left_lens") / f"{bill_id}.json",
        Path("right_lens") / f"{bill_id}.json",
        Path("analyses") / f"{bill_id}.json",
        Path("citation_audit") / f"{bill_id}.json",
    ]
    data_root = ROOT / "data"
    copied = []
    for rel in rels:
        src = data_root / rel
        if not src.exists():
            continue
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel.as_posix())
    _atomic_write_json(tmp / "manifest.json", {"bill_id": bill_id, "audit_status": audit_report.status, "files": copied})
    hold.parent.mkdir(parents=True, exist_ok=True)
    if hold.exists():
        shutil.rmtree(hold, ignore_errors=True)
    tmp.replace(hold)
    return hold


def author_generic_advocacy(bill_id: str) -> int:
    lp = ROOT / "data" / "left_lens" / f"{bill_id}.json"
    rp = ROOT / "data" / "right_lens" / f"{bill_id}.json"
    mp = ROOT / "data" / "money" / f"{bill_id}.json"
    pp = ROOT / "data" / "power" / f"{bill_id}.json"
    left, right = _load(lp), _load(rp)
    money_payload = _load(mp) if mp.exists() else {}
    power_payload = _load(pp) if pp.exists() else {}
    money_by = {x.get("anchor_id"): x for x in money_payload.get("findings", [])}
    power_by = {x.get("anchor_id"): x for x in power_payload.get("findings", [])}
    right_by = {x.get("anchor_id"): x for x in right.get("candidates", [])}
    authored = 0
    ordered = sorted(left.get("candidates", []), key=lambda x: (-len(x.get("evidence_layers_present", [])), -float(x.get("confidence", 0))))
    for item in ordered:
        aid = item.get("anchor_id")
        peer = right_by.get(aid)
        if not peer or authored >= 12:
            continue
        domains = item.get("expert_domains") or ["general_legislative"]
        domain = domains[0] if domains[0] in LEFT_THEMES else "general_legislative"
        packet = meaning.best(money_by.get(aid), power_by.get(aid))
        left_case, right_case = pass26_intelligence.substantive_lens_pair(packet)
        if not left_case or not right_case:
            # Fail closed: do not manufacture a political dispute from topic metadata alone.
            continue
        item["public_interpretation"] = left_case
        peer["public_interpretation"] = right_case
        provenance = "Pass 26 same-anchor substantive advocacy frame grounded in the structured source-bound effect; classified INTERPRETATION and subject to skeptic/referee review"
        item["public_interpretation_provenance"] = provenance
        peer["public_interpretation_provenance"] = provenance
        authored += 1
    _write(lp, left); _write(rp, right)
    return authored


def run_generic(bill_id: str) -> dict:
    meta = selected_bill(bill_id)
    if not meta:
        manifest_entry = ingest.load_source_manifest().get(bill_id)
        if not manifest_entry:
            raise KeyError(f"No registered or curated bill '{bill_id}'")
        meta = {
            "package_id": manifest_entry.get("law_number") or manifest_entry.get("official_identifier") or bill_id,
            "version_label": manifest_entry.get("version") or "Official enacted text",
        }
    source = ingest.SOURCE_DIR / f"{bill_id}.txt"
    if not source.exists():
        raise FileNotFoundError("Selected official bill text has not been downloaded")
    tracker = StageTracker(bill_id, STATUS_DIR, 19)
    ing = tracker.run("ingest", "Ingest selected official GovInfo bill text", lambda: ingest.ingest_manifest_bill(bill_id), lambda x: f"{x.line_count:,} lines")
    seg = tracker.run("segment", "Segment titles, subtitles, chapters, and sections", lambda: segment.segment_ingested_bill(bill_id), lambda x: f"{x.segment_count:,} structural blocks")
    anc = tracker.run("anchors", "Build exact citation anchors", lambda: citations.build_anchor_index(bill_id), lambda x: f"{len(x.anchors):,} anchors")
    trans = tracker.run("translate", "Run plain-English translator", lambda: translator.translate_bill(bill_id), lambda x: f"{len(x.translations):,} translation packets")
    mon = tracker.run("money", "Extract money mechanics", lambda: money.extract_bill(bill_id), lambda x: f"{len(x.findings):,} findings")
    pwr = tracker.run("power", "Extract power and authority mechanics", lambda: power.extract_bill(bill_id), lambda x: f"{len(x.findings):,} findings")
    bar = tracker.run("barrel", "Run Barrel Scan candidate detector", lambda: barrel_scan.scan_bill(bill_id), lambda x: f"{len(x.candidates):,} candidates")
    top = tracker.run("topics", "Route provisions to dynamic topic experts", lambda: topic_expert.review_bill(bill_id), lambda x: f"{len(x.reviews):,} reviews")
    tracker.run("left", "Build Left Lens packets", lambda: left_lens.build_left_lens(bill_id), lambda x: f"{len(x.candidates):,} candidates")
    tracker.run("right", "Build Right Lens packets", lambda: right_lens.build_right_lens(bill_id), lambda x: f"{len(x.candidates):,} candidates")
    authored = tracker.run("advocacy", "Attach source-bound generic interpretations", lambda: author_generic_advocacy(bill_id), lambda x: f"{x:,} matched pairs")
    sk = tracker.run("skeptic", "Run Investigative Skeptic", lambda: skeptic.build_skeptic_review(bill_id), lambda x: f"{len(x.packets):,} packets")
    ref = tracker.run("referee", "Run Neutral Referee", lambda: referee.build_referee_review(bill_id), lambda x: f"{len(x.decisions):,} decisions")
    syn = tracker.run("synthesis", "Build five-panel synthesis", lambda: synthesis.synthesize_bill(bill_id), lambda x: f"{x.selected_count:,} public claims; {x.analysis_status}")
    ext = tracker.run("external", "Pull official external evidence", lambda: external_evidence.collect_external_evidence(bill_id), lambda x: f"CBO={x['lanes']['cbo']['status']}; JCT={x['lanes']['jct']['status']}; USAspending={x['lanes']['usaspending']['status']}")
    con = tracker.run("consequence", "Build consequence evidence context", lambda: consequence.build_consequence_context(bill_id), lambda x: f"coverage confidence {x['consequence_confidence']:.3f}")
    red = tracker.run("red_team", "Run political-bias and selection-quality red team", lambda: red_team.audit_analysis(bill_id), lambda x: f"{x.status}; score {x.score:.3f}")
    aud = tracker.run("audit", "Run hallucination and citation audit", lambda: audit.audit_bill(bill_id), lambda x: f"{x.status}; {x.citations_checked}/{x.public_claim_count} citations reverified")
    # Pass 31.6.2.1: make the Stage-18 artifact durable BEFORE any release decision.
    # This does not alter audit status; it only guarantees failed diagnostics survive.
    _atomic_write_json(audit.AUDIT_DIR / f"{bill_id}.json", asdict(aud))
    if aud.status == "fail":
        hold_dir = _persist_failed_audit_bundle(bill_id, aud)
        print(f"      held audit persisted: {audit.AUDIT_DIR / (bill_id + '.json')}")
        print(f"      durable forensic bundle: {hold_dir}")
    if aud.findings:
        print("      citation audit findings:")
        for finding in aud.findings:
            where = f" panel={finding.panel}" if finding.panel else ""
            anchor = f" anchor={finding.anchor_id}" if finding.anchor_id else ""
            print(f"        [{finding.severity.upper()}] {finding.code}{where}{anchor}: {finding.message}")
        if aud.status == "fail":
            print(f"      forensic command: RUN_CITATION_FORENSICS_PASS31_6_2.bat (bill={bill_id})")
    else:
        print("      citation audit findings: none")
    chal = tracker.run("challenge", "Run hostile context and comprehension challenge", lambda: challenge.audit_analysis(bill_id), lambda x: f"{x.status}; score {x.score:.3f}")
    release_ok = syn.analysis_status == "verified" and red.status != "fail" and aud.status != "fail" and chal.status != "fail"
    progress = tracker.finish("complete" if release_ok else "release_hold")
    result = {
        "schema_version": "27.0", "bill_id": bill_id, "package_id": meta["package_id"],
        "source_sha256": ing.sha256, "source_bytes": ing.byte_count, "source_lines": ing.line_count,
        "segments": seg.segment_count, "anchors": len(anc.anchors), "translations": len(trans.translations),
        "money_findings": len(mon.findings), "power_findings": len(pwr.findings), "barrel_candidates": len(bar.candidates),
        "topic_reviews": len(top.reviews), "advocacy_pairs_authored": authored, "skeptic_packets": len(sk.packets),
        "referee_decisions": len(ref.decisions), "analysis_status": syn.analysis_status, "public_claims": syn.selected_count,
        "red_team_status": red.status, "red_team_score": red.score, "red_team_critical_count": red.critical_count,
        "red_team_warning_count": red.warning_count, "citation_audit_status": aud.status, "challenge_status": chal.status, "challenge_score": chal.score, "external_evidence": {k: v.get("status") for k, v in ext.get("lanes", {}).items()}, "consequence_confidence": con.get("consequence_confidence"), "challenge_blocker_count": chal.blocker_count, "challenge_important_count": chal.important_count,
        "citation_audit_critical_count": aud.critical_count, "citation_audit_warning_count": aud.warning_count,
        "citations_reverified": aud.citations_checked, "public_claims_reproduced": aud.upstream_claims_reproduced,
        "missing_public_lanes": syn.missing_public_lanes, "elapsed_seconds": progress["elapsed_seconds"],
        "stage_timings": {r["key"]: r["elapsed_seconds"] for r in progress["stages"]},
        "source_scope_note": f"Analyzes GovInfo package {meta['package_id']} ({meta['version_label']}) as selected; later or earlier bill versions are separate documents.",
    }
    _write(STATUS_DIR / f"{bill_id}.json", result)
    return result

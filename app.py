import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from engine import citizen_view
from engine.ingest import source_status
from engine.segment import segment_status
from engine.citations import citation_status, resolve_anchor
from engine.translator import translator_status
from engine.money import money_status
from engine.power import power_status
from engine.barrel_scan import barrel_status
from engine.topic_expert import topic_status
from engine.left_lens import left_status
from engine.right_lens import right_status
from engine.skeptic import skeptic_status
from engine.referee import referee_status
from engine.synthesis import synthesis_status
from engine.evidence import evidence_payload, evidence_status
from engine.aca_end_to_end import aca_status
from engine.obbba_end_to_end import obbba_status
from engine.red_team import red_team_status
from engine.audit import audit_status
from engine.challenge import challenge_status
from engine.external_evidence import external_status
from engine.consequence import consequence_status
from engine.build_orchestrator import build_status, library_build_status, start_build, verified_build_summary, cache_forensics
from engine.bill_search import search_bills, register_selected_bill, dynamic_bills
from engine.showcase_release import restore_all_showcases, persistent_store_root

ROOT = Path(__file__).resolve().parent
PUBLIC_MUSEUM = os.environ.get("BILL_XRAY_PUBLIC_MUSEUM", "0").strip().lower() in {"1", "true", "yes", "on"}
# historical surface compatibility: "surface_pass": "31.5"
app = FastAPI(title="Bill X-Ray")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")

with open(ROOT / "data" / "bills.json", encoding="utf-8") as f:
    STATIC_BILLS = json.load(f)
# Pass 30.2: restore compatible verified showcase releases before Page 1 asks
# whether ACA/OBBBA are instant exhibits. The persistent store lives outside the
# replaceable application folder, so verified prebuilds survive upgrades.
SHOWCASE_RESTORE = restore_all_showcases()
print(f"Bill X-Ray project root: {ROOT}")
print(f"Bill X-Ray persistent showcase store: {persistent_store_root()}")
for _sid in ("aca", "ira", "tcja", "obbba"):
    _r = SHOWCASE_RESTORE.get(_sid, {})
    print(f"{_sid.upper()} showcase handoff: persistent={_r.get('state', 'missing')} restored={_r.get('restored', False)}")


def all_bills():
    seen = set()
    merged = []
    for bill in dynamic_bills() + STATIC_BILLS:
        if bill["id"] not in seen:
            seen.add(bill["id"]); merged.append(bill)
    return merged

def find_bill(bill_id: str):
    return next((b for b in all_bills() if b["id"] == bill_id), None)

class SearchSelection(BaseModel):
    search_token: str = Field(min_length=6, max_length=80)
    package_id: str = Field(min_length=8, max_length=120)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # Pass 29: the public landing page is a focused demonstration, not a catalog.
    showcase_order = ("aca", "ira", "tcja", "obbba")
    by_id = {b["id"]: b for b in STATIC_BILLS}
    bills = [by_id[bill_id] for bill_id in showcase_order if bill_id in by_id]
    return templates.TemplateResponse("index.html", {"request": request, "bills": bills, "build_statuses": library_build_status([b["id"] for b in bills])})


@app.get("/bill/{bill_id}", response_class=HTMLResponse)
def bill(request: Request, bill_id: str):
    bill = find_bill(bill_id)
    if not bill:
        raise HTTPException(404, "Bill not found")
    analysis_path = ROOT / "data" / "analyses" / f"{bill_id}.json"
    analysis = {"analysis_status": "not_generated", "panels": []}
    if analysis_path.exists():
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    bill_status = build_status(bill_id)
    # Pass 28.1: a synthesis can be internally "verified" while a later release gate
    # places the report on hold. Never render those public claims as released output.
    if bill_status.get("state") != "verified":
        analysis = {"analysis_status": "hold" if bill_status.get("state") == "hold" else "not_generated", "panels": []}
    public_claim_count = sum(len(panel.get("claims", [])) for panel in analysis.get("panels", []))
    return templates.TemplateResponse(
        "bill.html", {
            "request": request,
            "bill": bill,
            "analysis": analysis,
            "public_claim_count": public_claim_count,
            "build_summary": verified_build_summary(bill_id) if bill_status.get("state") == "verified" else {},
            "bill_build_status": bill_status,
            "external_evidence": external_status(bill_id) if bill_status.get("state") == "verified" else {"status":"not_generated","lanes":{}},
            "consequence": consequence_status(bill_id) if bill_status.get("state") == "verified" else {"status":"not_generated"},
            "citizen": citizen_view.build(analysis) if analysis.get("analysis_status") == "verified" else {"core":[],"money":[],"power":[],"scrutiny":[],"questions":[],"lenses":[]},
        }
    )


@app.get("/api/showcase-handoff")
def api_showcase_handoff():
    """Pass 30.2 diagnostics for persistent verified showcase adoption/restoration."""
    return {
        "project_root": str(ROOT),
        "persistent_store": str(persistent_store_root()),
        "restore": SHOWCASE_RESTORE,
        "runtime": {bill_id: build_status(bill_id) for bill_id in ("aca", "ira", "tcja", "obbba")},
    }


@app.get("/api/build-status/{bill_id}")
def api_build_status(bill_id: str):
    """Pass 21 product-facing build readiness/progress for one bill."""
    if not find_bill(bill_id):
        raise HTTPException(404, "Bill not found")
    return build_status(bill_id)


@app.get("/api/cache-forensics/{bill_id}")
def api_cache_forensics(bill_id: str):
    """Pass 21.3: explain exactly why a historical verified build can or cannot be adopted."""
    if not find_bill(bill_id):
        raise HTTPException(404, "Bill not found")
    return cache_forensics(bill_id)


@app.post("/api/build/{bill_id}", status_code=202)
def api_start_build(bill_id: str):
    """Pass 21: acquire the official source and run the shared evidence pipeline in the background."""
    if PUBLIC_MUSEUM:
        raise HTTPException(404, "Not available on the curated public museum.")
    if not find_bill(bill_id):
        raise HTTPException(404, "Bill not found")
    try:
        return start_build(bill_id)
    except KeyError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/search-bills")
def api_search_bills(q: str = ""):
    """Pass 22: keyword/citation search across official GovInfo congressional bill versions."""
    if PUBLIC_MUSEUM:
        raise HTTPException(404, "Not available on the curated public museum.")
    try:
        return search_bills(q, limit=8)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/search-select", status_code=201)
def api_search_select(selection: SearchSelection):
    """Confirm one exact GovInfo bill version and register it for the shared build pipeline."""
    if PUBLIC_MUSEUM:
        raise HTTPException(404, "Not available on the curated public museum.")
    try:
        bill = register_selected_bill(selection.search_token, selection.package_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"bill": bill, "build": build_status(bill["id"])}


@app.get("/api/external-evidence/{bill_id}")
def api_external_evidence(bill_id: str):
    if not find_bill(bill_id):
        raise HTTPException(404, "Bill not found")
    return external_status(bill_id)


@app.get("/api/consequence/{bill_id}")
def api_consequence(bill_id: str):
    if not find_bill(bill_id):
        raise HTTPException(404, "Bill not found")
    return consequence_status(bill_id)


@app.get("/api/source-status")
def api_source_status():
    """Pass 2 readiness endpoint; reports local source and ingestion presence only."""
    return source_status()


@app.get("/api/health")
def api_health():
    """Health check used by the launcher and automated smoke tests."""
    return {"status": "ok", "app": "BILL X-RAY", "pass": "31", "release": "31", "build_pass": "31", "surface_pass": "31.6", "project_root": str(ROOT), "showcase_store": str(persistent_store_root())}


@app.get("/api/segment-status")
def api_segment_status():
    """Pass 3 readiness endpoint for structural segmentation artifacts."""
    return segment_status()


@app.get("/api/citation-status")
def api_citation_status():
    """Pass 4 readiness endpoint for deterministic exact citation anchors."""
    return citation_status()


@app.get("/api/citation/{bill_id}/{anchor_id}")
def api_citation(bill_id: str, anchor_id: str):
    """Resolve an anchor and verify it against the current canonical source text."""
    try:
        return resolve_anchor(bill_id, anchor_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/translator-status")
def api_translator_status():
    """Pass 5 readiness endpoint for evidence-preserving plain-English translation."""
    return translator_status()


@app.get("/api/money-status")
def api_money_status():
    """Pass 6 readiness endpoint for source-bound monetary provision extraction."""
    return money_status()


@app.get("/api/power-status")
def api_power_status():
    """Pass 7 readiness endpoint for source-bound power / authority extraction."""
    return power_status()


@app.get("/api/barrel-status")
def api_barrel_status():
    """Pass 8 readiness endpoint for evidence-bound Barrel Scan review candidates."""
    return barrel_status()


@app.get("/api/topic-status")
def api_topic_status():
    """Pass 9 readiness endpoint for dynamic provision-level topic-expert routing."""
    return topic_status()


@app.get("/api/left-status")
def api_left_status():
    """Pass 10 readiness endpoint for source-bound progressive advocacy packets."""
    return left_status()

@app.get("/api/right-status")
def api_right_status():
    """Pass 11 readiness endpoint for source-bound conservative advocacy packets."""
    return right_status()

@app.get("/api/skeptic-status")
def api_skeptic_status():
    """Pass 12 readiness endpoint for paired adversarial advocacy review."""
    return skeptic_status()



@app.get("/api/referee-status")
def api_referee_status():
    """Pass 13 readiness endpoint for Neutral Referee adjudication packets."""
    return referee_status()


@app.get("/api/synthesis-status")
def api_synthesis_status():
    """Pass 14 readiness endpoint for referee-bound five-panel synthesis."""
    return synthesis_status()


@app.get("/api/evidence-status")
def api_evidence_status():
    """Pass 15 readiness endpoint for one-click evidence drawer/source navigation."""
    return evidence_status()


@app.get("/api/aca-status")
def api_aca_status():
    """Pass 16 readiness endpoint for the ACA full-chain proving-ground run."""
    return aca_status()


@app.get("/api/obbba-status")
def api_obbba_status():
    """Pass 17 readiness endpoint for the Public Law 119-21 full-chain proving-ground run."""
    return obbba_status()


@app.get("/api/red-team-status")
def api_red_team_status():
    """Pass 18 political-bias and selection-quality red-team status."""
    return red_team_status()


@app.get("/api/audit-status")
def api_audit_status():
    """Pass 19 hallucination/citation release-audit status."""
    return audit_status()


@app.get("/api/challenge-status")
def api_challenge_status():
    """Pass 27 hostile multi-bill/context-prosecutor status."""
    return challenge_status()


@app.get("/api/evidence/{bill_id}/{anchor_id}")
def api_evidence(bill_id: str, anchor_id: str):
    """Resolve and re-verify exact source text for the public evidence drawer."""
    try:
        return evidence_payload(bill_id, anchor_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

"""Pass 21.1: shared bill build orchestrator + persistent verified cache + progress UX.

A first-time bill build may be expensive. Once a bill survives the referee, red team,
and citation audit, its evidence artifacts remain on disk and a cache manifest records
that verified result. Subsequent visits open instantly unless the canonical source has
changed or required evidence artifacts are missing.
"""
from __future__ import annotations

import hashlib
import json
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from engine.aca_end_to_end import run_aca
from engine.obbba_end_to_end import run_obbba
from tools.fetch_aca_source import ensure_aca_source
from tools.fetch_obbba_source import ensure_obbba_source
from tools.fetch_ira_source import ensure_ira_source
from tools.fetch_tcja_source import ensure_tcja_source
from engine.bill_search import selected_bill, ensure_dynamic_source
from engine.generic_end_to_end import run_generic

ROOT = Path(__file__).resolve().parents[1]
STATUS_DIR = ROOT / "data" / "build_status"
PROGRESS_DIR = ROOT / "data" / "end_to_end"
CACHE_DIR = ROOT / "data" / "analysis_cache"
ANALYSES_DIR = ROOT / "data" / "analyses"
SOURCE_DIR = ROOT / "data" / "source_documents"
INGESTED_DIR = ROOT / "data" / "ingested"
ANCHOR_DIR = ROOT / "data" / "citation_anchors"
SYNTHESIS_DIR = ROOT / "data" / "synthesis"
RED_TEAM_DIR = ROOT / "data" / "red_team"
EXTERNAL_DIR = ROOT / "data" / "external_evidence"
CONSEQUENCE_DIR = ROOT / "data" / "consequence"
AUDIT_DIR = ROOT / "data" / "citation_audit"
CHALLENGE_DIR = ROOT / "data" / "challenge"
PUBLIC_ANALYSIS_VERSION = "30.1-fiscal-object-provenance"


@dataclass(frozen=True)
class BuilderSpec:
    bill_id: str
    fetch: Callable[[], Path]
    run: Callable[[], dict]


BUILDERS: dict[str, BuilderSpec] = {
    "aca": BuilderSpec("aca", ensure_aca_source, run_aca),
    "obbba": BuilderSpec("obbba", ensure_obbba_source, run_obbba),
    "ira": BuilderSpec("ira", ensure_ira_source, lambda: run_generic("ira")),
    "tcja": BuilderSpec("tcja", ensure_tcja_source, lambda: run_generic("tcja")),
}

def _builder_spec(bill_id: str) -> BuilderSpec | None:
    if bill_id in BUILDERS:
        return BUILDERS[bill_id]
    if selected_bill(bill_id):
        return BuilderSpec(bill_id, lambda: ensure_dynamic_source(bill_id), lambda: run_generic(bill_id))
    return None

# Historical stage weights are only used for ETA/progress presentation. They do not
# affect analysis or release decisions. ACA weights reflect the first full-scale run;
# OBBBA weights reflect its repeatedly measured ~100-second run.
STAGE_ORDER = [
    "ingest", "segment", "anchors", "translate", "money", "power", "barrel", "topics",
    "left", "right", "advocacy", "skeptic", "referee", "synthesis", "external", "consequence", "red_team", "audit", "challenge",
]
STAGE_LABELS = {
    "ingest": "Reading the official bill",
    "segment": "Mapping the bill's structure",
    "anchors": "Locking exact citations",
    "translate": "Translating dense legal language",
    "money": "Tracing money, taxes, grants, and revenue",
    "power": "Mapping power, duties, and authority",
    "barrel": "Scanning for riders, carve-outs, and surprises",
    "topics": "Routing provisions to subject-matter experts",
    "left": "Building the strongest progressive reading",
    "right": "Building the strongest conservative reading",
    "advocacy": "Binding both readings to the same evidence",
    "skeptic": "Letting the investigative skeptic attack weak claims",
    "referee": "Running the neutral referee",
    "synthesis": "Building the public X-Ray",
    "external": "Pulling official CBO, JCT, and USAspending context",
    "consequence": "Comparing statute to expected and observed consequence",
    "red_team": "Red-teaming political and selection bias",
    "audit": "Re-verifying every public citation",
    "challenge": "Prosecuting missing context and weak public explanations",
}
STAGE_DESCRIPTIONS = {
    "ingest": "Bill X-Ray is reading the canonical government text and fingerprinting the source.",
    "segment": "It is separating titles, subtitles, chapters, and sections so later claims keep their legal context.",
    "anchors": "Every future claim is being tied to an exact, tamper-evident location in the bill.",
    "translate": "Dense statutory mechanics are being converted into bounded plain English without dropping qualifiers.",
    "money": "The system is finding appropriations, taxes, credits, grants, rescissions, subsidies, loans, and revenue mechanics.",
    "power": "It is checking who receives duties, discretion, rulemaking power, enforcement authority, or new limits.",
    "barrel": "Potential riders, narrow carve-outs, concentrated beneficiaries, and scope surprises are being scored for scrutiny.",
    "topics": "Each provision is being routed to the subject experts it actually needs rather than labeling the whole bill at once.",
    "left": "The progressive advocate is building its strongest good-faith interpretation from the locked evidence record.",
    "right": "The conservative advocate is building its strongest good-faith interpretation from that same evidence record.",
    "advocacy": "Bill X-Ray is confirming both political lanes use identical underlying statutory evidence.",
    "skeptic": "The skeptic is attacking unsupported leaps, rhetorical inflation, cherry-picking, and missing context on both sides.",
    "referee": "The referee is deciding what is TEXT, direct effect, interpretation, disputed, or still unknown.",
    "synthesis": "Only referee-approved material is being ranked into the simple public report.",
    "external": "Official external sources are being queried in separate lanes: CBO cost estimates, JCT revenue estimates, and USAspending implementation context.",
    "consequence": "Bill X-Ray is measuring consequence-evidence coverage while keeping statute, estimates, and observed spending explicitly separate.",
    "red_team": "The finished report is being attacked for political asymmetry, weak selection, trivial findings, and legalese.",
    "audit": "Every displayed claim is being reconstructed from its source and every citation is being re-opened before release.",
    "challenge": "The Context Prosecutor is checking whether definitions, exceptions, amendments, or cross-references could make an otherwise accurate sentence misleading.",
}
ACA_STAGE_ESTIMATES = {
    "ingest": 1, "segment": 1, "anchors": 15, "translate": 95, "money": 95, "power": 95,
    "barrel": 95, "topics": 95, "left": 95, "right": 95, "advocacy": 2, "skeptic": 3,
    "referee": 4, "synthesis": 30, "external": 15, "consequence": 2, "red_team": 2, "audit": 3, "challenge": 2,
}
OBBBA_STAGE_ESTIMATES = {
    "ingest": 1, "segment": 1, "anchors": 2, "translate": 13, "money": 13, "power": 15,
    "barrel": 13, "topics": 13, "left": 13, "right": 13, "advocacy": 1, "skeptic": 1,
    "referee": 1, "synthesis": 13, "external": 15, "consequence": 2, "red_team": 1, "audit": 1, "challenge": 1,
}
DEFAULT_STAGE_ESTIMATES = {key: 20 for key in STAGE_ORDER}

_LOCK = threading.Lock()
_RUNNING: set[str] = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_path(bill_id: str) -> Path:
    return STATUS_DIR / f"{bill_id}.json"


def _progress_path(bill_id: str) -> Path:
    return PROGRESS_DIR / f"{bill_id}_progress.json"


def _cache_path(bill_id: str) -> Path:
    return CACHE_DIR / f"{bill_id}.json"


def _write_status(bill_id: str, payload: dict) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"bill_id": bill_id, "updated_at": _now(), **payload}
    _status_path(bill_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _analysis_status(bill_id: str) -> str:
    path = ANALYSES_DIR / f"{bill_id}.json"
    if not path.exists():
        return "not_generated"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("analysis_status", "not_generated")
    except (OSError, json.JSONDecodeError):
        return "not_generated"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _required_cache_artifacts(bill_id: str) -> list[Path]:
    # A verified cache is a release artifact, not merely a rendered page.  Require
    # the source spine plus the two independent release gates that approved it.
    return [
        SOURCE_DIR / f"{bill_id}.txt",
        INGESTED_DIR / f"{bill_id}.json",
        ANCHOR_DIR / f"{bill_id}.json",
        ANALYSES_DIR / f"{bill_id}.json",
        RED_TEAM_DIR / f"{bill_id}.json",
        AUDIT_DIR / f"{bill_id}.json",
        CHALLENGE_DIR / f"{bill_id}.json",
    ]


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cache_forensics(bill_id: str) -> dict:
    """Explain, check by check, whether a historical verified build is adoptable.

    Pass 21.3 intentionally derives release eligibility from durable artifacts rather
    than requiring a cache manifest or one specific historical end-to-end file. This
    lets legitimate Pass 19/20/21 builds survive upgrades while still failing closed
    if the source fingerprint, red team, citation audit, or public analysis disagrees.
    """
    source = SOURCE_DIR / f"{bill_id}.txt"
    ingested_path = INGESTED_DIR / f"{bill_id}.json"
    analysis_path = ANALYSES_DIR / f"{bill_id}.json"
    synthesis_path = SYNTHESIS_DIR / f"{bill_id}.json"
    red_path = RED_TEAM_DIR / f"{bill_id}.json"
    audit_path = AUDIT_DIR / f"{bill_id}.json"
    challenge_path = CHALLENGE_DIR / f"{bill_id}.json"
    result_path = PROGRESS_DIR / f"{bill_id}.json"

    ingested = _read_json(ingested_path) if ingested_path.exists() else None
    analysis = _read_json(analysis_path) if analysis_path.exists() else None
    synthesis = _read_json(synthesis_path) if synthesis_path.exists() else None
    red = _read_json(red_path) if red_path.exists() else None
    audit = _read_json(audit_path) if audit_path.exists() else None
    challenge = _read_json(challenge_path) if challenge_path.exists() else None
    result = _read_json(result_path) if result_path.exists() else None

    actual_sha = _sha256(source) if source.exists() else None
    ingested_sha = (ingested or {}).get("sha256")
    result_sha = (result or {}).get("source_sha256")
    fingerprint_candidates = [v for v in (ingested_sha, result_sha) if v]
    fingerprint_ok = bool(actual_sha and fingerprint_candidates and all(v == actual_sha for v in fingerprint_candidates))

    analysis_ok = (analysis or {}).get("analysis_status") == "verified"
    synthesis_status = (synthesis or {}).get("analysis_status")
    synthesis_ok = synthesis is None or synthesis_status == "verified"
    red_status = (red or {}).get("status")
    red_ok = red_status in {"pass", "pass_with_warnings"} and int((red or {}).get("critical_count", 0) or 0) == 0
    audit_status = (audit or {}).get("status")
    audit_public = int((audit or {}).get("public_claim_count", 0) or 0)
    audit_checked = int((audit or {}).get("citations_checked", 0) or 0)
    audit_ok = (
        audit_status in {"pass", "pass_with_warnings"}
        and int((audit or {}).get("critical_count", 0) or 0) == 0
        and audit_public > 0
        and audit_checked >= audit_public
    )
    challenge_ok = (challenge or {}).get("status") in {"pass", "pass_with_findings"} and int((challenge or {}).get("blocker_count", 0) or 0) == 0
    result_ok = result is None or (
        result.get("analysis_status") == "verified"
        and result.get("red_team_status") != "fail"
        and result.get("citation_audit_status") != "fail"
    )
    anchors_ok = (ANCHOR_DIR / f"{bill_id}.json").exists()

    checks = {
        "official_source_present": source.exists(),
        "ingested_artifact_present": ingested is not None,
        "citation_anchors_present": anchors_ok,
        "analysis_verified": analysis_ok,
        "synthesis_not_contradictory": synthesis_ok,
        "red_team_passed": red_ok,
        "citation_audit_passed": audit_ok,
        "hostile_challenge_passed": challenge_ok,
        "source_fingerprint_matches": fingerprint_ok,
        "end_to_end_result_not_contradictory": result_ok,
    }
    failures = [key for key, ok in checks.items() if not ok]
    public_claims = audit_public or int((synthesis or {}).get("selected_count", 0) or 0)
    return {
        "bill_id": bill_id,
        "adoptable": not failures,
        "checks": checks,
        "failures": failures,
        "source_sha256": actual_sha,
        "ingested_sha256": ingested_sha,
        "result_sha256": result_sha,
        "red_team_status": red_status,
        "citation_audit_status": audit_status,
        "challenge_status": (challenge or {}).get("status"),
        "citations_checked": audit_checked,
        "public_claims": public_claims,
        "historical_result_present": result is not None,
    }


def _write_cache_manifest(bill_id: str, result: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    source = SOURCE_DIR / f"{bill_id}.txt"
    payload = {
        "schema_version": "21.1",
        "bill_id": bill_id,
        "cached_at": _now(),
        "source_sha256": result.get("source_sha256") or (_sha256(source) if source.exists() else None),
        "analysis_status": result.get("analysis_status"),
        "red_team_status": result.get("red_team_status"),
        "citation_audit_status": result.get("citation_audit_status"),
        "challenge_status": result.get("challenge_status"),
        "public_claims": result.get("public_claims"),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "public_analysis_version": PUBLIC_ANALYSIS_VERSION,
    }
    _cache_path(bill_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _adopt_legacy_verified_cache(bill_id: str) -> bool:
    """Adopt any durable, fully verified historical build without recomputing it."""
    forensic = cache_forensics(bill_id)
    if not forensic["adoptable"]:
        return False
    result_path = PROGRESS_DIR / f"{bill_id}.json"
    result = _read_json(result_path) or {}
    result = {
        **result,
        "source_sha256": forensic["source_sha256"],
        "analysis_status": "verified",
        "red_team_status": forensic["red_team_status"],
        "citation_audit_status": forensic["citation_audit_status"],
        "challenge_status": forensic.get("challenge_status"),
        "public_claims": result.get("public_claims") or forensic["public_claims"],
    }
    _write_cache_manifest(bill_id, result)
    return True


def cache_status(bill_id: str) -> dict:
    path = _cache_path(bill_id)
    if not path.exists() and not _adopt_legacy_verified_cache(bill_id):
        forensic = cache_forensics(bill_id)
        return {
            "cached": False,
            "cache_valid": False,
            "cache_reason": "historical_build_not_adoptable",
            "cache_forensics": forensic,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"cached": True, "cache_valid": False, "cache_reason": "cache_manifest_unreadable"}
    missing = [str(p.relative_to(ROOT)) if ROOT in p.parents else str(p) for p in _required_cache_artifacts(bill_id) if not p.exists()]
    if missing:
        return {"cached": True, "cache_valid": False, "cache_reason": "required_artifact_missing", "missing_artifacts": missing}
    if _analysis_status(bill_id) != "verified":
        return {"cached": True, "cache_valid": False, "cache_reason": "analysis_not_verified"}
    source = SOURCE_DIR / f"{bill_id}.txt"
    expected = payload.get("source_sha256")
    if not expected:
        return {"cached": True, "cache_valid": False, "cache_reason": "source_fingerprint_missing"}
    if _sha256(source) != expected:
        return {"cached": True, "cache_valid": False, "cache_reason": "source_fingerprint_changed"}
    if payload.get("public_analysis_version") != PUBLIC_ANALYSIS_VERSION:
        return {"cached": True, "cache_valid": False, "cache_reason": "public_analysis_version_changed", "required_version": PUBLIC_ANALYSIS_VERSION}
    return {"cached": True, "cache_valid": True, "cache": payload}


def verified_build_summary(bill_id: str) -> dict | None:
    """Return compact, user-facing proof of work for a completed verified run.

    The durable end-to-end result lives at data/end_to_end/<bill_id>.json.
    The sibling <bill_id>_progress.json is intentionally stage telemetry only.
    Keeping those roles separate prevents a finished build from losing its proof-of-work
    summary after the live progress tracker clears its current-stage fields.
    """
    path = PROGRESS_DIR / f"{bill_id}.json"
    if not path.exists() or _analysis_status(bill_id) != "verified":
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if result.get("analysis_status") != "verified":
        return None
    reviewed = result.get("translations") or result.get("topic_reviews") or result.get("segments")
    return {
        "source_lines": result.get("source_lines"),
        "segments": result.get("segments"),
        "reviewed": reviewed,
        "public_claims": result.get("public_claims"),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "public_analysis_version": PUBLIC_ANALYSIS_VERSION,
        "red_team_status": result.get("red_team_status"),
        "citation_audit_status": result.get("citation_audit_status"),
        "challenge_status": result.get("challenge_status"),
        "challenge_score": result.get("challenge_score"),
        "challenge_blocker_count": result.get("challenge_blocker_count"),
        "challenge_important_count": result.get("challenge_important_count"),
    }


def _stage_estimates(bill_id: str) -> dict[str, float]:
    if bill_id == "aca":
        return ACA_STAGE_ESTIMATES
    if bill_id == "obbba":
        return OBBBA_STAGE_ESTIMATES
    return DEFAULT_STAGE_ESTIMATES


def _product_progress(bill_id: str, runtime_state: str) -> dict | None:
    if runtime_state == "fetching":
        return {
            "percent": 2,
            "stage_index": 0,
            "total_stages": 19,
            "stage_key": "fetch",
            "stage_label": "Securing the official government source",
            "stage_description": "Bill X-Ray is acquiring the canonical government text before analysis begins.",
            "elapsed_seconds": 0,
            "eta_seconds": None,
            "eta_label": "Calculating after the first checks finish",
            "completed": [],
        }
    path = _progress_path(bill_id)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    estimates = _stage_estimates(bill_id)
    total_weight = sum(estimates.get(key, 20) for key in STAGE_ORDER)
    completed_records = [r for r in raw.get("stages", []) if r.get("status") == "complete"]
    completed_keys = [r.get("key") for r in completed_records]
    completed_weight = sum(estimates.get(key, 20) for key in completed_keys)
    current_key = raw.get("current_stage")
    current_elapsed = float(raw.get("current_stage_elapsed_seconds") or 0)
    current_weight = estimates.get(current_key, 20) if current_key else 0
    current_fraction = min(current_elapsed / max(current_weight, 1), 0.92) if current_key else 0
    weighted_done = completed_weight + current_weight * current_fraction
    percent = min(99, max(1, round(100 * weighted_done / max(total_weight, 1))))
    elapsed = float(raw.get("elapsed_seconds") or 0)
    # Blend the static stage model with observed throughput after enough work has finished.
    baseline_remaining = max(total_weight - weighted_done, 0)
    observed_scale = 1.0
    if completed_weight >= total_weight * 0.08 and elapsed > 0:
        observed_scale = max(0.65, min(2.5, elapsed / max(weighted_done, 1)))
    eta = round(baseline_remaining * observed_scale)
    if raw.get("state") in {"complete", "release_hold"}:
        percent = 100
        eta = 0
    idx = raw.get("current_stage_index") or (len(completed_records) + 1 if current_key else len(completed_records))
    label = raw.get("current_label") or STAGE_LABELS.get(current_key) or "Checking the evidence pipeline"
    description = STAGE_DESCRIPTIONS.get(current_key, "Bill X-Ray is continuing the evidence pipeline.")
    completed = [
        {
            "key": r.get("key"),
            "label": STAGE_LABELS.get(r.get("key"), r.get("label") or r.get("key")),
            "summary": r.get("summary"),
            "elapsed_seconds": r.get("elapsed_seconds"),
        }
        for r in completed_records
    ]
    if eta <= 0:
        eta_label = "Finishing now"
    elif eta < 90:
        eta_label = f"About {max(1, round(eta / 30) * 30)} seconds remaining"
    else:
        low = max(1, round((eta * 0.8) / 60))
        high = max(low + 1, round((eta * 1.25) / 60))
        eta_label = f"About {low}–{high} minutes remaining"
    return {
        "percent": percent,
        "stage_index": idx,
        "total_stages": raw.get("total_stages", 19),
        "stage_key": current_key,
        "stage_label": label,
        "stage_description": description,
        "elapsed_seconds": round(elapsed),
        "eta_seconds": eta,
        "eta_label": eta_label,
        "completed": completed,
    }


def is_buildable(bill_id: str) -> bool:
    return _builder_spec(bill_id) is not None


def build_status(bill_id: str) -> dict:
    if not is_buildable(bill_id):
        return {
            "bill_id": bill_id,
            "buildable": False,
            "state": "catalog_only",
            "analysis_status": _analysis_status(bill_id),
            "message": "Official-source build wiring is not connected for this catalog bill yet.",
        }

    analysis = _analysis_status(bill_id)
    with _LOCK:
        running = bill_id in _RUNNING
    cached = cache_status(bill_id) if not running else {"cached": False, "cache_valid": False}
    state = "running" if running else ("verified" if analysis == "verified" and cached.get("cache_valid") else "ready")
    payload = {
        "bill_id": bill_id,
        "buildable": True,
        "state": state,
        "analysis_status": analysis,
        "cached": bool(cached.get("cache_valid")),
        "message": "Verified cached analysis — opens instantly." if state == "verified" else (
            "Building official-source analysis…" if state == "running" else "Ready to build from the official source."
        ),
    }
    path = _status_path(bill_id)
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            payload.update(saved)
            payload["buildable"] = True
            payload["analysis_status"] = analysis
            if running:
                payload["state"] = "running"
            elif analysis == "verified" and cached.get("cache_valid"):
                payload["state"] = "verified"
                payload["cached"] = True
                payload["message"] = "Verified cached analysis — opens instantly."
        except (OSError, json.JSONDecodeError):
            pass
    if payload.get("state") in {"fetching", "running", "queued"}:
        payload["progress"] = _product_progress(bill_id, payload.get("state"))
    return payload


def _worker(bill_id: str) -> None:
    spec = _builder_spec(bill_id)
    if spec is None:
        raise KeyError(f"Bill '{bill_id}' does not yet have official-source build wiring")
    try:
        progress_path = _progress_path(bill_id)
        if progress_path.exists():
            progress_path.unlink()
        _write_status(bill_id, {"state": "fetching", "analysis_status": _analysis_status(bill_id), "message": "Acquiring official government text…"})
        source_path = spec.fetch()
        _write_status(bill_id, {"state": "running", "analysis_status": _analysis_status(bill_id), "message": "Official source acquired. Running the evidence pipeline…", "source_path": str(source_path)})
        result = spec.run()
        release_ok = (
            result.get("analysis_status") == "verified"
            and result.get("red_team_status") != "fail"
            and result.get("citation_audit_status") != "fail"
            and result.get("challenge_status") != "fail"
        )
        if release_ok:
            _write_cache_manifest(bill_id, result)
        _write_status(
            bill_id,
            {
                "state": "verified" if release_ok else "hold",
                "analysis_status": result.get("analysis_status", "draft"),
                "message": "Verified analysis cached and ready." if release_ok else "Pipeline finished, but a release gate is holding this report.",
                "cached": release_ok,
                "result": result,
            },
        )
    except Exception as exc:
        _write_status(
            bill_id,
            {
                "state": "error",
                "analysis_status": _analysis_status(bill_id),
                "message": str(exc),
                "error_type": type(exc).__name__,
                "traceback": traceback.format_exc(limit=8),
            },
        )
    finally:
        with _LOCK:
            _RUNNING.discard(bill_id)


def start_build(bill_id: str) -> dict:
    if not is_buildable(bill_id):
        raise KeyError(f"Bill '{bill_id}' does not yet have official-source build wiring")
    cached = cache_status(bill_id)
    if cached.get("cache_valid"):
        return build_status(bill_id)
    with _LOCK:
        already_running = bill_id in _RUNNING
        if not already_running:
            _RUNNING.add(bill_id)
    if already_running:
        return build_status(bill_id)
    _write_status(bill_id, {"state": "queued", "analysis_status": _analysis_status(bill_id), "message": "Build queued…"})
    thread = threading.Thread(target=_worker, args=(bill_id,), name=f"bill-xray-build-{bill_id}", daemon=True)
    thread.start()
    return build_status(bill_id)


def library_build_status(bill_ids: list[str]) -> dict[str, dict]:
    return {bill_id: build_status(bill_id) for bill_id in bill_ids}

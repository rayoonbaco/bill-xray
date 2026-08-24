"""Pass 30.2.2: verified artifact schema reconciliation and migration.

A public showcase may have been produced by an older compatible Bill X-Ray pass whose
release evidence used slightly different JSON field names.  This module reconciles
those historical schemas into one canonical release assessment, but it never creates
missing evidence or treats a summary flag as a substitute for the actual source spine.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE_IDS = ("aca", "ira", "tcja", "obbba")
COMPATIBLE_PUBLIC_ANALYSIS_VERSION = "30.1-fiscal-object-provenance"

_ARTIFACTS = (
    "source_documents/{bill_id}.txt",
    "ingested/{bill_id}.json",
    "citation_anchors/{bill_id}.json",
    "analyses/{bill_id}.json",
    "synthesis/{bill_id}.json",
    "red_team/{bill_id}.json",
    "citation_audit/{bill_id}.json",
    "challenge/{bill_id}.json",
    "end_to_end/{bill_id}.json",
    "analysis_cache/{bill_id}.json",
    "external_evidence/{bill_id}.json",
    "consequence/{bill_id}.json",
    "translations/{bill_id}.json",
    "money/{bill_id}.json",
    "power/{bill_id}.json",
    "barrel_scan/{bill_id}.json",
    "left_lens/{bill_id}.json",
    "right_lens/{bill_id}.json",
    "referee/{bill_id}.json",
)
_REQUIRED_GROUPS = {"source_documents", "citation_anchors", "analyses", "red_team", "citation_audit", "challenge"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def persistent_store_root() -> Path:
    override = os.environ.get("BILL_XRAY_SHOWCASE_STORE")
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "Bill_XRay" / "showcase_releases"
    return Path.home() / ".bill_xray" / "showcase_releases"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _artifact_specs(bill_id: str) -> list[tuple[str, Path]]:
    return [(t.format(bill_id=bill_id), ROOT / "data" / t.format(bill_id=bill_id)) for t in _ARTIFACTS]


def _release_dir(bill_id: str) -> Path:
    return persistent_store_root() / bill_id


def _manifest_path(bill_id: str) -> Path:
    return _release_dir(bill_id) / "release_manifest.json"


def _first(payloads: list[dict], *keys: str):
    for payload in payloads:
        for key in keys:
            value = payload.get(key)
            if value is not None:
                return value
    return None


def _status_is_pass(value, allowed: set[str]) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in allowed


def reconcile_working_release(bill_id: str) -> dict:
    """Normalize compatible historical artifact schemas into a strict release decision.

    Summary files may corroborate a component status, but they cannot replace the
    physical source, citation anchors, public analysis, or gate artifact needed to
    render and audit the exhibit.
    """
    data = ROOT / "data"
    paths = {
        "source": data / "source_documents" / f"{bill_id}.txt",
        "ingested": data / "ingested" / f"{bill_id}.json",
        "anchors": data / "citation_anchors" / f"{bill_id}.json",
        "analysis": data / "analyses" / f"{bill_id}.json",
        "synthesis": data / "synthesis" / f"{bill_id}.json",
        "red": data / "red_team" / f"{bill_id}.json",
        "audit": data / "citation_audit" / f"{bill_id}.json",
        "challenge": data / "challenge" / f"{bill_id}.json",
        "e2e": data / "end_to_end" / f"{bill_id}.json",
        "cache": data / "analysis_cache" / f"{bill_id}.json",
    }
    j = {name: (_read_json(path) or {}) for name, path in paths.items() if name not in {"source", "anchors"}}
    e2e, cache = j.get("e2e", {}), j.get("cache", {})

    source_present = paths["source"].exists()
    anchors_present = paths["anchors"].exists()
    analysis_present = paths["analysis"].exists() and bool(j.get("analysis"))
    red_present = paths["red"].exists() and bool(j.get("red"))
    audit_present = paths["audit"].exists() and bool(j.get("audit"))
    challenge_present = paths["challenge"].exists() and bool(j.get("challenge"))

    analysis_status = _first([j.get("analysis", {}), j.get("synthesis", {}), e2e, cache], "analysis_status", "status")
    red_status = _first([j.get("red", {}), e2e, cache], "status", "red_team_status")
    red_critical = _first([j.get("red", {}), e2e], "critical_count", "red_team_critical_count") or 0
    audit_status = _first([j.get("audit", {}), e2e, cache], "status", "citation_audit_status")
    audit_critical = _first([j.get("audit", {}), e2e], "critical_count", "citation_audit_critical_count") or 0
    challenge_status = _first([j.get("challenge", {}), e2e, cache], "status", "challenge_status")
    challenge_blockers = _first([j.get("challenge", {}), e2e], "blocker_count", "challenge_blocker_count") or 0

    synthesis_version = str(j.get("synthesis", {}).get("synthesizer_version") or "")
    checks = {
        "official_source_present": source_present,
        "citation_anchors_present": anchors_present,
        "analysis_artifact_present": analysis_present,
        "analysis_verified": str(analysis_status or "").lower() == "verified",
        "red_team_artifact_present": red_present,
        "red_team_passed": _status_is_pass(red_status, {"pass", "pass_with_warnings"}) and int(red_critical) == 0,
        "citation_audit_artifact_present": audit_present,
        "citation_audit_passed": _status_is_pass(audit_status, {"pass", "pass_with_warnings"}) and int(audit_critical) == 0,
        "challenge_artifact_present": challenge_present,
        "hostile_challenge_passed": _status_is_pass(challenge_status, {"pass", "pass_with_findings"}) and int(challenge_blockers) == 0,
    }

    actual_sha = _sha256(paths["source"]) if source_present else None
    fingerprints = []
    for payload in (j.get("ingested", {}), e2e, cache):
        for key in ("sha256", "source_sha256"):
            value = payload.get(key)
            if value:
                fingerprints.append(str(value))
    checks["source_fingerprint_matches"] = bool(actual_sha and fingerprints and all(v == actual_sha for v in fingerprints))

    audit = j.get("audit", {})
    public_count = int(_first([audit, e2e, cache], "public_claim_count", "public_claims") or 0)
    checked = int(_first([audit, e2e], "citations_checked", "citations_reverified") or 0)
    if public_count or checked:
        checks["citation_counts_reconcile"] = bool(public_count > 0 and checked >= public_count)

    failures = [name for name, ok in checks.items() if not ok]
    missing_physical = [
        name for name, ok in {
            "official_source": source_present,
            "citation_anchors": anchors_present,
            "analysis": analysis_present,
            "red_team": red_present,
            "citation_audit": audit_present,
            "challenge": challenge_present,
        }.items() if not ok
    ]
    return {
        "bill_id": bill_id,
        "adoptable": not failures,
        "checks": checks,
        "failures": failures,
        "missing_physical_artifacts": missing_physical,
        "normalized": {
            "analysis_status": analysis_status,
            "red_team_status": red_status,
            "red_team_critical_count": int(red_critical),
            "citation_audit_status": audit_status,
            "citation_audit_critical_count": int(audit_critical),
            "challenge_status": challenge_status,
            "challenge_blocker_count": int(challenge_blockers),
            "public_claims": public_count,
            "citations_checked": checked,
            "source_sha256": actual_sha,
            "synthesizer_version": synthesis_version or None,
        },
    }


def _validate_working_release(bill_id: str) -> tuple[bool, str]:
    report = reconcile_working_release(bill_id)
    if report["adoptable"]:
        return True, "verified_by_schema_reconciliation"
    return False, "reconciliation:" + ",".join(report["failures"])


def publish_verified_showcase(bill_id: str) -> dict:
    if bill_id not in SHOWCASE_IDS:
        raise ValueError(f"{bill_id!r} is not a public showcase")
    report = reconcile_working_release(bill_id)
    if not report["adoptable"]:
        raise RuntimeError("Cannot publish persistent showcase release: reconciliation:" + ",".join(report["failures"]))

    release_dir = _release_dir(bill_id)
    tmp_dir = release_dir.with_name(release_dir.name + ".tmp")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    manifest_files: list[dict] = []
    present_groups: set[str] = set()
    for rel, source in _artifact_specs(bill_id):
        if not source.exists():
            continue
        target = tmp_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest_files.append({"path": rel, "sha256": _sha256(target), "bytes": target.stat().st_size})
        present_groups.add(Path(rel).parts[0])
    missing = sorted(_REQUIRED_GROUPS - present_groups)
    if missing:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError("Verified release is missing required artifact groups: " + ", ".join(missing))
    manifest = {
        "schema_version": "31",
        "bill_id": bill_id,
        "published_at": _now(),
        "public_analysis_version": COMPATIBLE_PUBLIC_ANALYSIS_VERSION,
        "source_project_root": str(ROOT),
        "normalized_release": report["normalized"],
        "files": manifest_files,
    }
    (tmp_dir / "release_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    release_dir.parent.mkdir(parents=True, exist_ok=True)
    if release_dir.exists():
        shutil.rmtree(release_dir)
    tmp_dir.replace(release_dir)
    return {"status": "published", "bill_id": bill_id, "store": str(release_dir), "files": len(manifest_files)}


def persistent_release_status(bill_id: str) -> dict:
    manifest_path = _manifest_path(bill_id)
    if not manifest_path.exists():
        return {"bill_id": bill_id, "state": "missing", "store": str(_release_dir(bill_id))}
    manifest = _read_json(manifest_path)
    if not manifest:
        return {"bill_id": bill_id, "state": "invalid", "reason": "manifest_unreadable", "store": str(_release_dir(bill_id))}
    if manifest.get("public_analysis_version") != COMPATIBLE_PUBLIC_ANALYSIS_VERSION:
        return {"bill_id": bill_id, "state": "invalid", "reason": "analysis_version_incompatible", "store": str(_release_dir(bill_id))}
    files = manifest.get("files") or []
    if not files:
        return {"bill_id": bill_id, "state": "invalid", "reason": "manifest_empty", "store": str(_release_dir(bill_id))}
    groups = {Path(str(item.get("path") or "")).parts[0] for item in files if item.get("path")}
    missing_groups = sorted(_REQUIRED_GROUPS - groups)
    if missing_groups:
        return {"bill_id": bill_id, "state": "invalid", "reason": "required_groups:" + ",".join(missing_groups), "store": str(_release_dir(bill_id))}
    for item in files:
        path = _release_dir(bill_id) / str(item.get("path") or "")
        if not path.exists():
            return {"bill_id": bill_id, "state": "invalid", "reason": f"missing:{item.get('path')}", "store": str(_release_dir(bill_id))}
        if item.get("sha256") and _sha256(path) != item.get("sha256"):
            return {"bill_id": bill_id, "state": "invalid", "reason": f"checksum:{item.get('path')}", "store": str(_release_dir(bill_id))}
    return {"bill_id": bill_id, "state": "verified", "store": str(_release_dir(bill_id)), "files": len(files)}


def restore_verified_showcase(bill_id: str) -> dict:
    status = persistent_release_status(bill_id)
    if status.get("state") != "verified":
        report = reconcile_working_release(bill_id)
        if report["adoptable"]:
            published = publish_verified_showcase(bill_id)
            status = persistent_release_status(bill_id)
            status["adopted_from_working_folder"] = True
            status["published_store"] = published.get("store")
            status["reconciliation"] = report
        else:
            return {**status, "restored": False, "working_reason": "reconciliation:" + ",".join(report["failures"]), "reconciliation": report}
    manifest = _read_json(_manifest_path(bill_id)) or {}
    copied = 0
    for item in manifest.get("files") or []:
        rel = str(item["path"])
        source = _release_dir(bill_id) / rel
        target = ROOT / "data" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and item.get("sha256") and _sha256(target) == item.get("sha256"):
            continue
        shutil.copy2(source, target)
        copied += 1
    return {**status, "restored": True, "copied": copied}


def restore_all_showcases() -> dict[str, dict]:
    return {bill_id: restore_verified_showcase(bill_id) for bill_id in SHOWCASE_IDS}

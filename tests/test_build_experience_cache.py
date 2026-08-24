import json
from pathlib import Path

import engine.build_orchestrator as bo


def test_product_progress_uses_weighted_stage_costs(tmp_path, monkeypatch):
    monkeypatch.setattr(bo, "PROGRESS_DIR", tmp_path)
    payload = {
        "bill_id": "aca",
        "state": "running",
        "current_stage": "power",
        "current_label": "Extract power and authority mechanics",
        "current_stage_index": 6,
        "current_stage_elapsed_seconds": 40,
        "completed_stages": 5,
        "total_stages": 16,
        "elapsed_seconds": 285,
        "stages": [
            {"key": "ingest", "label": "x", "status": "complete", "elapsed_seconds": .1, "summary": "58,479 lines"},
            {"key": "segment", "label": "x", "status": "complete", "elapsed_seconds": .2, "summary": "2,602 blocks"},
            {"key": "anchors", "label": "x", "status": "complete", "elapsed_seconds": 13.5, "summary": "2,602 anchors"},
            {"key": "translate", "label": "x", "status": "complete", "elapsed_seconds": 90.3, "summary": "2,258 translations"},
            {"key": "money", "label": "x", "status": "complete", "elapsed_seconds": 88.5, "summary": "861 findings"},
        ],
    }
    (tmp_path / "aca_progress.json").write_text(json.dumps(payload))
    p = bo._product_progress("aca", "running")
    assert 25 <= p["percent"] <= 50
    assert p["stage_index"] == 6
    assert "power" in p["stage_label"].lower() or "authority" in p["stage_label"].lower()
    assert p["eta_seconds"] > 0
    assert len(p["completed"]) == 5


def test_verified_cache_requires_source_fingerprint_and_evidence_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(bo, "ROOT", tmp_path)
    monkeypatch.setattr(bo, "CACHE_DIR", tmp_path / "data" / "analysis_cache")
    monkeypatch.setattr(bo, "ANALYSES_DIR", tmp_path / "data" / "analyses")
    monkeypatch.setattr(bo, "SOURCE_DIR", tmp_path / "data" / "source_documents")
    monkeypatch.setattr(bo, "INGESTED_DIR", tmp_path / "data" / "ingested")
    monkeypatch.setattr(bo, "ANCHOR_DIR", tmp_path / "data" / "citation_anchors")
    monkeypatch.setattr(bo, "SYNTHESIS_DIR", tmp_path / "data" / "synthesis")
    monkeypatch.setattr(bo, "RED_TEAM_DIR", tmp_path / "data" / "red_team")
    monkeypatch.setattr(bo, "AUDIT_DIR", tmp_path / "data" / "citation_audit")
    monkeypatch.setattr(bo, "CHALLENGE_DIR", tmp_path / "data" / "challenge")
    for d in [bo.CACHE_DIR, bo.ANALYSES_DIR, bo.SOURCE_DIR, bo.INGESTED_DIR, bo.ANCHOR_DIR, bo.SYNTHESIS_DIR, bo.RED_TEAM_DIR, bo.AUDIT_DIR, bo.CHALLENGE_DIR]: d.mkdir(parents=True, exist_ok=True)
    source = bo.SOURCE_DIR / "aca.txt"; source.write_text("official source", encoding="utf-8")
    (bo.INGESTED_DIR / "aca.json").write_text(json.dumps({"sha256":bo._sha256(source)}), encoding="utf-8")
    (bo.ANCHOR_DIR / "aca.json").write_text("{}", encoding="utf-8")
    (bo.ANALYSES_DIR / "aca.json").write_text(json.dumps({"analysis_status":"verified"}), encoding="utf-8")
    (bo.RED_TEAM_DIR / "aca.json").write_text(json.dumps({"status":"pass","critical_count":0}), encoding="utf-8")
    (bo.AUDIT_DIR / "aca.json").write_text(json.dumps({"status":"pass","critical_count":0,"public_claim_count":15,"citations_checked":15}), encoding="utf-8")
    (bo.CHALLENGE_DIR / "aca.json").write_text(json.dumps({"status":"pass","blocker_count":0,"important_count":0}), encoding="utf-8")
    bo._write_cache_manifest("aca", {"source_sha256": bo._sha256(source), "analysis_status":"verified", "red_team_status":"pass", "citation_audit_status":"pass", "challenge_status":"pass"})
    assert bo.cache_status("aca")["cache_valid"] is True
    source.write_text("changed source", encoding="utf-8")
    assert bo.cache_status("aca")["cache_valid"] is False
    assert bo.cache_status("aca")["cache_reason"] == "source_fingerprint_changed"


def test_pass32_home_moves_live_progress_off_public_museum_surface():
    root = Path(__file__).resolve().parents[1]
    html = (root / "templates" / "index.html").read_text(encoding="utf-8")
    bill = (root / "templates" / "bill.html").read_text(encoding="utf-8")
    js = (root / "static" / "build_controls.js").read_text(encoding="utf-8")
    assert "data-build-session" not in html
    assert "CURATED PUBLIC EXHIBITS" in html
    assert "data-build-session" in bill
    assert "/api/build-status/" in js


def test_curated_release_never_ships_placeholder_showcase_analysis():
    root = Path(__file__).resolve().parents[1]
    for bill_id in ("aca", "ira", "tcja", "obbba"):
        path = root / "data" / "analyses" / f"{bill_id}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload.get("analysis_status") == "verified"
        assert any(panel.get("claims") for panel in payload.get("panels", []))


def test_pass21_verified_build_is_adopted_without_rebuild(tmp_path, monkeypatch):
    monkeypatch.setattr(bo, "ROOT", tmp_path)
    monkeypatch.setattr(bo, "CACHE_DIR", tmp_path / "data" / "analysis_cache")
    monkeypatch.setattr(bo, "PROGRESS_DIR", tmp_path / "data" / "end_to_end")
    monkeypatch.setattr(bo, "ANALYSES_DIR", tmp_path / "data" / "analyses")
    monkeypatch.setattr(bo, "SOURCE_DIR", tmp_path / "data" / "source_documents")
    monkeypatch.setattr(bo, "INGESTED_DIR", tmp_path / "data" / "ingested")
    monkeypatch.setattr(bo, "ANCHOR_DIR", tmp_path / "data" / "citation_anchors")
    monkeypatch.setattr(bo, "SYNTHESIS_DIR", tmp_path / "data" / "synthesis")
    monkeypatch.setattr(bo, "RED_TEAM_DIR", tmp_path / "data" / "red_team")
    monkeypatch.setattr(bo, "AUDIT_DIR", tmp_path / "data" / "citation_audit")
    monkeypatch.setattr(bo, "CHALLENGE_DIR", tmp_path / "data" / "challenge")
    for d in [bo.CACHE_DIR, bo.PROGRESS_DIR, bo.ANALYSES_DIR, bo.SOURCE_DIR, bo.INGESTED_DIR, bo.ANCHOR_DIR, bo.SYNTHESIS_DIR, bo.RED_TEAM_DIR, bo.AUDIT_DIR, bo.CHALLENGE_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    source = bo.SOURCE_DIR / "aca.txt"
    source.write_text("official source", encoding="utf-8")
    (bo.INGESTED_DIR / "aca.json").write_text(json.dumps({"sha256":bo._sha256(source)}), encoding="utf-8")
    (bo.ANCHOR_DIR / "aca.json").write_text("{}", encoding="utf-8")
    (bo.ANALYSES_DIR / "aca.json").write_text(json.dumps({"analysis_status":"verified"}), encoding="utf-8")
    (bo.RED_TEAM_DIR / "aca.json").write_text(json.dumps({"status":"pass","critical_count":0}), encoding="utf-8")
    (bo.AUDIT_DIR / "aca.json").write_text(json.dumps({"status":"pass","critical_count":0,"public_claim_count":15,"citations_checked":15}), encoding="utf-8")
    (bo.CHALLENGE_DIR / "aca.json").write_text(json.dumps({"status":"pass","blocker_count":0,"important_count":0}), encoding="utf-8")
    result = {"source_sha256": bo._sha256(source), "analysis_status":"verified", "red_team_status":"pass", "citation_audit_status":"pass", "challenge_status":"pass", "public_claims":15}
    (bo.PROGRESS_DIR / "aca.json").write_text(json.dumps(result), encoding="utf-8")
    status = bo.cache_status("aca")
    assert status["cache_valid"] is True
    assert (bo.CACHE_DIR / "aca.json").exists()


def test_real_pass21_artifact_layout_adopts_verified_aca_without_rebuild(tmp_path, monkeypatch):
    monkeypatch.setattr(bo, "ROOT", tmp_path)
    monkeypatch.setattr(bo, "CACHE_DIR", tmp_path / "data" / "analysis_cache")
    monkeypatch.setattr(bo, "PROGRESS_DIR", tmp_path / "data" / "end_to_end")
    monkeypatch.setattr(bo, "ANALYSES_DIR", tmp_path / "data" / "analyses")
    monkeypatch.setattr(bo, "SOURCE_DIR", tmp_path / "data" / "source_documents")
    monkeypatch.setattr(bo, "INGESTED_DIR", tmp_path / "data" / "ingested")
    monkeypatch.setattr(bo, "ANCHOR_DIR", tmp_path / "data" / "citation_anchors")
    monkeypatch.setattr(bo, "SYNTHESIS_DIR", tmp_path / "data" / "synthesis")
    monkeypatch.setattr(bo, "RED_TEAM_DIR", tmp_path / "data" / "red_team")
    monkeypatch.setattr(bo, "AUDIT_DIR", tmp_path / "data" / "citation_audit")
    monkeypatch.setattr(bo, "CHALLENGE_DIR", tmp_path / "data" / "challenge")
    for directory in [bo.CACHE_DIR, bo.PROGRESS_DIR, bo.ANALYSES_DIR, bo.SOURCE_DIR, bo.INGESTED_DIR, bo.ANCHOR_DIR, bo.SYNTHESIS_DIR, bo.RED_TEAM_DIR, bo.AUDIT_DIR, bo.CHALLENGE_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
    source = bo.SOURCE_DIR / "aca.txt"
    source.write_text("official ACA bytes", encoding="utf-8")
    (bo.INGESTED_DIR / "aca.json").write_text(json.dumps({"bill_id":"aca","sha256":bo._sha256(source)}), encoding="utf-8")
    (bo.ANCHOR_DIR / "aca.json").write_text("{}", encoding="utf-8")
    (bo.ANALYSES_DIR / "aca.json").write_text(json.dumps({"analysis_status":"verified"}), encoding="utf-8")
    (bo.RED_TEAM_DIR / "aca.json").write_text(json.dumps({"status":"pass","critical_count":0}), encoding="utf-8")
    (bo.AUDIT_DIR / "aca.json").write_text(json.dumps({"status":"pass","critical_count":0,"public_claim_count":15,"citations_checked":15}), encoding="utf-8")
    (bo.CHALLENGE_DIR / "aca.json").write_text(json.dumps({"status":"pass","blocker_count":0,"important_count":0}), encoding="utf-8")
    result = {
        "bill_id":"aca",
        "source_sha256":bo._sha256(source),
        "source_lines":58479,
        "translations":2258,
        "analysis_status":"verified",
        "public_claims":15,
        "red_team_status":"pass",
        "citation_audit_status":"pass",
    }
    (bo.PROGRESS_DIR / "aca.json").write_text(json.dumps(result), encoding="utf-8")
    status = bo.build_status("aca")
    assert status["state"] == "verified"
    assert status["cached"] is True
    assert (bo.CACHE_DIR / "aca.json").exists()
    summary = bo.verified_build_summary("aca")
    assert summary["source_lines"] == 58479
    assert summary["reviewed"] == 2258
    assert summary["public_claims"] == 15


def test_pass21_3_forensics_identifies_missing_release_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(bo, "ROOT", tmp_path)
    for name, rel in [
        ("CACHE_DIR","analysis_cache"),("PROGRESS_DIR","end_to_end"),("ANALYSES_DIR","analyses"),
        ("SOURCE_DIR","source_documents"),("INGESTED_DIR","ingested"),("ANCHOR_DIR","citation_anchors"),
        ("SYNTHESIS_DIR","synthesis"),("RED_TEAM_DIR","red_team"),("AUDIT_DIR","citation_audit")]:
        d = tmp_path / "data" / rel; d.mkdir(parents=True, exist_ok=True); monkeypatch.setattr(bo, name, d)
    source = bo.SOURCE_DIR / "aca.txt"; source.write_text("official", encoding="utf-8")
    (bo.INGESTED_DIR / "aca.json").write_text(json.dumps({"sha256":bo._sha256(source)}), encoding="utf-8")
    (bo.ANCHOR_DIR / "aca.json").write_text("{}", encoding="utf-8")
    (bo.ANALYSES_DIR / "aca.json").write_text(json.dumps({"analysis_status":"verified"}), encoding="utf-8")
    (bo.RED_TEAM_DIR / "aca.json").write_text(json.dumps({"status":"pass","critical_count":0}), encoding="utf-8")
    forensic = bo.cache_forensics("aca")
    assert forensic["adoptable"] is False
    assert "citation_audit_passed" in forensic["failures"]
    assert forensic["checks"]["source_fingerprint_matches"] is True


def test_pass21_3_exposes_cache_forensics_endpoint_and_health_version():
    from fastapi.testclient import TestClient
    from app import app
    client = TestClient(app)
    assert client.get('/api/health').json()['pass'] == '31'
    payload = client.get('/api/cache-forensics/aca').json()
    assert payload['bill_id'] == 'aca'
    assert 'checks' in payload
    assert 'failures' in payload

import json
from pathlib import Path

import engine.build_orchestrator as bo


def test_proving_ground_bills_share_one_product_build_registry():
    assert set(bo.BUILDERS) == {"aca", "ira", "tcja", "obbba"}
    assert bo.is_buildable("aca") is True
    assert bo.is_buildable("obbba") is True
    assert bo.is_buildable("dodd-frank") is False


def test_catalog_bill_reports_explicit_not_wired_state():
    status = bo.build_status("dodd-frank")
    assert status["buildable"] is False
    assert status["state"] == "catalog_only"
    assert "not connected" in status["message"].lower()


def test_worker_records_verified_result_without_weakening_release_gates(tmp_path, monkeypatch):
    status_dir = tmp_path / "status"
    analysis_dir = tmp_path / "analyses"
    analysis_dir.mkdir()
    monkeypatch.setattr(bo, "STATUS_DIR", status_dir)
    monkeypatch.setattr(bo, "ANALYSES_DIR", analysis_dir)

    source = tmp_path / "bill.txt"
    source.write_text("official text")

    def fetch():
        return source

    def run():
        (analysis_dir / "aca.json").write_text(json.dumps({"analysis_status": "verified"}))
        return {
            "analysis_status": "verified",
            "red_team_status": "pass",
            "citation_audit_status": "pass",
        }

    monkeypatch.setitem(bo.BUILDERS, "aca", bo.BuilderSpec("aca", fetch, run))
    with bo._LOCK:
        bo._RUNNING.add("aca")
    bo._worker("aca")
    payload = json.loads((status_dir / "aca.json").read_text())
    assert payload["state"] == "verified"
    assert payload["analysis_status"] == "verified"
    assert "aca" not in bo._RUNNING


def test_worker_holds_release_when_red_team_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(bo, "STATUS_DIR", tmp_path / "status")
    monkeypatch.setattr(bo, "ANALYSES_DIR", tmp_path / "analyses")
    (tmp_path / "analyses").mkdir()
    source = tmp_path / "bill.txt"
    source.write_text("official text")

    def run():
        return {"analysis_status": "verified", "red_team_status": "fail", "citation_audit_status": "pass"}

    monkeypatch.setitem(bo.BUILDERS, "aca", bo.BuilderSpec("aca", lambda: source, run))
    with bo._LOCK:
        bo._RUNNING.add("aca")
    bo._worker("aca")
    payload = json.loads((tmp_path / "status" / "aca.json").read_text())
    assert payload["state"] == "hold"
    assert "release gate" in payload["message"].lower()


def test_pass21_home_exposes_real_build_controls_only_for_wired_bills():
    html = (Path(__file__).resolve().parents[1] / "templates" / "index.html").read_text()
    assert 'data-build-bill="{{bill.id}}"' not in html
    assert 'CURATED PUBLIC EXHIBITS' in html
    assert "Search GovInfo and choose the exact published version before analysis." not in html
    js = (Path(__file__).resolve().parents[1] / "static" / "build_controls.js").read_text()
    assert "/api/build/" in js
    assert "/api/build-status/" in js
    assert "window.location.assign" in js


def test_cache_requires_real_source_fingerprint(tmp_path, monkeypatch):
    import engine.build_orchestrator as bo
    source_dir = tmp_path / "source_documents"
    ingested_dir = tmp_path / "ingested"
    anchor_dir = tmp_path / "anchors"
    analyses_dir = tmp_path / "analyses"
    cache_dir = tmp_path / "cache"
    red_dir = tmp_path / "red_team"
    audit_dir = tmp_path / "citation_audit"
    challenge_dir = tmp_path / "challenge"
    synthesis_dir = tmp_path / "synthesis"
    for d in (source_dir, ingested_dir, anchor_dir, analyses_dir, cache_dir, red_dir, audit_dir, challenge_dir, synthesis_dir):
        d.mkdir()
    (source_dir / "aca.txt").write_text("official source", encoding="utf-8")
    (ingested_dir / "aca.json").write_text(json.dumps({"sha256": bo._sha256(source_dir / "aca.txt")}), encoding="utf-8")
    (anchor_dir / "aca.json").write_text("{}", encoding="utf-8")
    (analyses_dir / "aca.json").write_text('{"analysis_status":"verified"}', encoding="utf-8")
    (red_dir / "aca.json").write_text('{"status":"pass","critical_count":0}', encoding="utf-8")
    (audit_dir / "aca.json").write_text('{"status":"pass","critical_count":0,"public_claim_count":15,"citations_checked":15}', encoding="utf-8")
    (challenge_dir / "aca.json").write_text('{"status":"pass","blocker_count":0,"important_count":0}', encoding="utf-8")
    (cache_dir / "aca.json").write_text('{"bill_id":"aca","source_sha256":null}', encoding="utf-8")
    monkeypatch.setattr(bo, "SOURCE_DIR", source_dir)
    monkeypatch.setattr(bo, "INGESTED_DIR", ingested_dir)
    monkeypatch.setattr(bo, "ANCHOR_DIR", anchor_dir)
    monkeypatch.setattr(bo, "ANALYSES_DIR", analyses_dir)
    monkeypatch.setattr(bo, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(bo, "RED_TEAM_DIR", red_dir)
    monkeypatch.setattr(bo, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(bo, "CHALLENGE_DIR", challenge_dir)
    monkeypatch.setattr(bo, "SYNTHESIS_DIR", synthesis_dir)
    monkeypatch.setattr(bo, "PROGRESS_DIR", tmp_path / "missing_progress")
    status = bo.cache_status("aca")
    assert status["cache_valid"] is False
    assert status["cache_reason"] == "source_fingerprint_missing"


def test_verified_build_summary_exposes_proof_of_work(tmp_path, monkeypatch):
    import engine.build_orchestrator as bo
    analyses_dir = tmp_path / "analyses"
    progress_dir = tmp_path / "progress"
    analyses_dir.mkdir(); progress_dir.mkdir()
    (analyses_dir / "aca.json").write_text('{"analysis_status":"verified"}', encoding="utf-8")
    (progress_dir / "aca.json").write_text('{"analysis_status":"verified","source_lines":58479,"translations":2258,"public_claims":15,"red_team_status":"pass","citation_audit_status":"pass"}', encoding="utf-8")
    monkeypatch.setattr(bo, "ANALYSES_DIR", analyses_dir)
    monkeypatch.setattr(bo, "PROGRESS_DIR", progress_dir)
    summary = bo.verified_build_summary("aca")
    assert summary["source_lines"] == 58479
    assert summary["reviewed"] == 2258
    assert summary["public_claims"] == 15

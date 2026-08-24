from pathlib import Path

from engine.schemas import Citation, Claim
from engine.synthesis import Candidate, assemble_analysis, _public_language_ok

ROOT = Path(__file__).resolve().parents[1]


def _candidate(text, amount, score, anchor):
    cite = Citation(bill_id="demo", anchor_id=anchor, section="SEC. 1.", document_ref="local:x", location_marker="lines 1-2")
    claim = Claim(text=text, claim_class="DIRECT_EFFECT", confidence=.9, citations=[cite], direct_effect=True)
    return Candidate("follow_the_money", claim, score, anchor, "money", amount)


def test_follow_the_money_ranks_materiality_before_generic_score():
    base_cite = Citation(bill_id="demo", anchor_id="main", section="SEC. 1.", document_ref="local:x", location_marker="lines 1-2")
    candidates = [
        Candidate("what_it_really_does", Claim(text="Congress changes the program.", claim_class="TEXT", confidence=.9, citations=[base_cite]), 1, "main", "fixture"),
        _candidate("Congress provides $5 million for one program.", 5_000_000, 99, "small"),
        _candidate("Congress provides $250 billion for another program.", 250_000_000_000, 2, "large"),
        _candidate("Congress provides $1 billion for a third program.", 1_000_000_000, 3, "medium"),
    ]
    analysis = assemble_analysis("demo", candidates)
    money = next(p for p in analysis.panels if p.key == "follow_the_money")
    assert [c.citations[0].anchor_id for c in money.claims] == ["large", "medium", "small"]


def test_public_language_gate_rejects_front_page_legislative_edit_code():
    assert _public_language_ok("Congress provides $250 million to eligible States for grants.")
    assert not _public_language_ok("Subsection (a) is amended by striking paragraph (2) and inserting the following.")
    assert not _public_language_ok("The text shall read as follows: qualified opportunity zone business-- paragraph (4).")


def test_hold_state_is_review_not_rebuild_from_library():
    js = (ROOT / "static" / "build_controls.js").read_text(encoding="utf-8")
    home = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    bill = (ROOT / "templates" / "bill.html").read_text(encoding="utf-8")
    assert "button.dataset.buildState === 'hold' && !button.classList.contains('inline-build-button')" in js
    assert "Review hold" in home
    assert "Report held for review." in bill
    assert "Run analysis again" in bill


def test_pass28_1_versions_are_current():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    launcher = (ROOT / "START_BILL_XRAY.bat").read_text(encoding="utf-8")
    assert '"pass": "31"' in app
    assert "BILL X-RAY - PASS 31" in launcher


def test_held_verified_synthesis_is_not_rendered_publicly(tmp_path, monkeypatch):
    import json
    import app as app_module
    from fastapi.testclient import TestClient

    analyses = tmp_path / "data" / "analyses"
    analyses.mkdir(parents=True)
    (analyses / "demo.json").write_text(json.dumps({
        "analysis_status": "verified",
        "panels": [{"key": "what_it_really_does", "title": "What You Should Know", "claims": [{"text": "UNPUBLISHED SECRET CLAIM", "claim_class": "TEXT", "confidence": .9, "citations": []}]}],
    }), encoding="utf-8")
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    monkeypatch.setattr(app_module, "find_bill", lambda bill_id: {"id":"demo","short_title":"Demo Bill","year":"2026","category":"Test"} if bill_id == "demo" else None)
    monkeypatch.setattr(app_module, "build_status", lambda bill_id: {"bill_id":bill_id,"buildable":True,"state":"hold","analysis_status":"verified","message":"held"})
    monkeypatch.setattr(app_module, "verified_build_summary", lambda bill_id: {})
    response = TestClient(app_module.app).get("/bill/demo")
    assert response.status_code == 200
    assert "Report held for review." in response.text
    assert "UNPUBLISHED SECRET CLAIM" not in response.text

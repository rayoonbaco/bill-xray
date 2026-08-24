from engine.schemas import Citation, Claim
from engine import synthesis


def test_pass23_claim_can_carry_explanation_without_changing_evidence_identity():
    claim = Claim(
        text="In plain English: this section changes who can receive the benefit.",
        claim_class="DIRECT_EFFECT",
        confidence=0.91,
        citations=[Citation(bill_id="demo", anchor_id="a1", section="SEC. 1", document_ref="local:demo.txt", location_marker="lines 1-2")],
        direct_effect=True,
        why_it_matters="This changes who qualifies.",
        ordinary_explanation="The narrower rule may be a legitimate eligibility definition.",
        scrutiny_score=82.0,
    )
    assert claim.scrutiny_score == 82.0
    assert claim.citations[0].anchor_id == "a1"


def test_pass23_power_copy_uses_normal_language():
    text = synthesis._power_text({
        "actors": ["The Secretary"],
        "authority_types": ["rulemaking_authority"],
        "authority_direction": "expansion",
    })
    assert text.startswith("In plain English:")
    assert "explicit" not in text.lower()
    assert "mechanic" not in text.lower()
    assert "Secretary" in text


def test_pass23_scrutiny_includes_normal_explanation_and_score():
    ordinary = synthesis._ordinary_explanation({"labels": ["Narrow Carve-Out"]})
    assert "legitimate" in ordinary.lower()
    assert "does not show" in ordinary.lower()


def test_pass23_surface_centers_public_understanding_and_ranked_scrutiny():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    template = (root / "templates" / "bill.html").read_text(encoding="utf-8")
    assert "What You Should Know" in template
    assert "15-YEAR-OLD TEST" in template
    assert "What Deserves Scrutiny" in template
    assert "Could there be a normal explanation?" in template
    assert "scrutiny_score" in template

def test_pass23_cache_requires_current_public_intelligence_version(tmp_path, monkeypatch):
    import json
    import engine.build_orchestrator as bo
    source = tmp_path / "source_documents" / "demo.txt"
    source.parent.mkdir(parents=True)
    source.write_text("official text", encoding="utf-8")
    cache = tmp_path / "analysis_cache" / "demo.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"source_sha256": bo._sha256(source), "public_analysis_version": "22.0"}), encoding="utf-8")
    monkeypatch.setattr(bo, "ROOT", tmp_path)
    monkeypatch.setattr(bo, "SOURCE_DIR", source.parent)
    monkeypatch.setattr(bo, "CACHE_DIR", cache.parent)
    monkeypatch.setattr(bo, "_required_cache_artifacts", lambda bill_id: [])
    monkeypatch.setattr(bo, "_analysis_status", lambda bill_id: "verified")
    status = bo.cache_status("demo")
    assert status["cache_valid"] is False
    assert status["cache_reason"] == "public_analysis_version_changed"

import json
from pathlib import Path

import pytest

from engine.schemas import BillAnalysis, Citation, Claim, Panel
from engine.synthesis import Candidate, assemble_analysis, collect_candidates, synthesize_bill


def _citation(anchor="a1"):
    return Citation(
        bill_id="demo", anchor_id=anchor, section="SEC. 101.",
        document_ref="local:demo.txt", location_marker="lines 1-4"
    )


def _candidate(panel, text, *, score=1.0, anchor="a1", claim_class="TEXT", lens=None, source="fixture", barrel=False):
    kwargs = {}
    if barrel:
        kwargs.update(barrel_label="Scope Surprise", why_flagged="The section combines topical distance with another scrutiny signal.")
    claim = Claim(text=text, claim_class=claim_class, confidence=0.9, citations=[_citation(anchor)], lens=lens, **kwargs)
    return Candidate(panel, claim, score, anchor, source)


def _complete_candidates():
    return [
        _candidate("what_it_really_does", "The Secretary must establish the program.", score=3, anchor="a1"),
        _candidate("follow_the_money", "The section appropriates $10 million.", score=3, anchor="a2", claim_class="DIRECT_EFFECT"),
        _candidate("barrel_scan", "Scope Surprise: the section deserves closer inspection.", score=3, anchor="a3", claim_class="DIRECT_EFFECT", barrel=True),
        _candidate("who_wins_pays_power", "The Secretary receives rulemaking authority.", score=3, anchor="a4", claim_class="DIRECT_EFFECT"),
        _candidate("left_right_text", "A progressive reading emphasizes broad access and public accountability.", score=3, anchor="a1", claim_class="INTERPRETATION", lens="LEFT"),
        _candidate("left_right_text", "A conservative reading emphasizes limits, cost discipline, and delegated power.", score=3, anchor="a1", claim_class="INTERPRETATION", lens="RIGHT"),
        _candidate("left_right_text", "The Secretary must establish the program.", score=3, anchor="a1", claim_class="TEXT", lens="TEXT"),
    ]


def test_assemble_verified_analysis_has_exact_five_panel_surface():
    analysis = assemble_analysis("demo", _complete_candidates())
    assert analysis.analysis_status == "verified"
    assert [panel.key for panel in analysis.panels] == [
        "what_it_really_does", "follow_the_money", "barrel_scan",
        "who_wins_pays_power", "left_right_text"
    ]
    assert [claim.lens for claim in analysis.panels[-1].claims] == ["LEFT", "RIGHT", "TEXT"]


def test_synthesis_hard_caps_every_panel_at_three_claims():
    candidates = _complete_candidates()
    for i in range(8):
        candidates.append(_candidate("what_it_really_does", f"Distinct effect {i}.", score=2-i/10, anchor=f"x{i}"))
    analysis = assemble_analysis("demo", candidates)
    assert max(len(panel.claims) for panel in analysis.panels) <= 3


def test_synthesis_prefers_higher_ranked_claims():
    candidates = _complete_candidates()
    candidates.append(_candidate("what_it_really_does", "Highest-ranked effect.", score=99, anchor="top"))
    analysis = assemble_analysis("demo", candidates)
    assert analysis.panels[0].claims[0].text == "Highest-ranked effect."


def test_synthesis_deduplicates_same_public_claim():
    candidates = _complete_candidates()
    candidates += [
        _candidate("what_it_really_does", "Duplicate effect.", score=5, anchor="d1"),
        _candidate("what_it_really_does", "Duplicate effect!", score=4, anchor="d2"),
    ]
    analysis = assemble_analysis("demo", candidates)
    texts = [claim.text.lower().rstrip(".!") for claim in analysis.panels[0].claims]
    assert texts.count("duplicate effect") == 1


def test_verified_analysis_allows_empty_nonapplicable_specialty_panel():
    candidates = [c for c in _complete_candidates() if c.panel_key != "barrel_scan"]
    analysis = assemble_analysis("demo", candidates)
    assert analysis.analysis_status == "verified"
    barrel = next(panel for panel in analysis.panels if panel.key == "barrel_scan")
    assert barrel.claims == []


def test_missing_right_lens_keeps_report_draft():
    candidates = [c for c in _complete_candidates() if c.claim.lens != "RIGHT"]
    analysis = assemble_analysis("demo", candidates)
    assert analysis.analysis_status == "draft"


def test_verified_schema_rejects_wrong_lens_order():
    panels = assemble_analysis("demo", _complete_candidates()).panels
    lens = panels[-1]
    bad_lens = Panel(key=lens.key, title=lens.title, claims=[lens.claims[1], lens.claims[0], lens.claims[2]])
    with pytest.raises(ValueError, match="LEFT, RIGHT, TEXT"):
        BillAnalysis(bill_id="demo", analysis_status="verified", panels=panels[:-1] + [bad_lens])


def _write_index(path: Path, key: str, items: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({key: items}), encoding="utf-8")


def _decision(anchor="a1"):
    return {
        "bill_id": "demo", "anchor_id": anchor, "segment_id": "sec-1", "section_label": "SEC. 101.",
        "status": "synthesis_ready", "confidence": 0.9,
        "admissible_claim_classes": ["TEXT", "DIRECT_EFFECT", "INTERPRETATION", "DISPUTED", "UNKNOWN"],
        "text_lane": {"confidence": 0.96}, "direct_effect_lane": {"confidence": 0.86},
        "left_lane": {"status": "admissible_as_interpretation", "confidence": 0.86},
        "right_lane": {"status": "admissible_as_interpretation", "confidence": 0.86},
        "barrel_lane": {"status": "admissible_as_scrutiny_flag", "confidence": 0.82},
        "location_marker": "lines 1-4", "document_ref": "local:demo.txt", "source_url": "https://example.test/demo",
        "source_sha256": "a"*64, "text_sha256": "b"*64,
    }


def _mock_text_referee(monkeypatch, syn, text="“The Secretary shall establish the program.”"):
    from types import SimpleNamespace
    monkeypatch.setattr(
        syn.text_referee,
        "construct_text_referee",
        lambda bill_id, anchor_id: SimpleNamespace(status="constructed", text=text, confidence=0.99, reason=None),
    )


def test_collect_candidates_obeys_blocked_referee(tmp_path, monkeypatch):
    import engine.synthesis as syn
    dirs = {name: tmp_path/name for name in ["referee","translations","money","power","barrel","left","right"]}
    decision = _decision(); decision["status"] = "blocked"
    _write_index(dirs["referee"]/"demo.json", "decisions", [decision])
    for name, key in [("translations","translations"),("money","findings"),("power","findings"),("barrel","candidates"),("left","candidates"),("right","candidates")]:
        _write_index(dirs[name]/"demo.json", key, [])
    monkeypatch.setattr(syn, "REFEREE_DIR", dirs["referee"])
    monkeypatch.setattr(syn, "TRANSLATION_DIR", dirs["translations"])
    monkeypatch.setattr(syn, "MONEY_DIR", dirs["money"])
    monkeypatch.setattr(syn, "POWER_DIR", dirs["power"])
    monkeypatch.setattr(syn, "BARREL_DIR", dirs["barrel"])
    monkeypatch.setattr(syn, "LEFT_DIR", dirs["left"])
    monkeypatch.setattr(syn, "RIGHT_DIR", dirs["right"])
    assert collect_candidates("demo") == []


def test_collect_candidates_does_not_turn_lens_prompt_into_public_argument(tmp_path, monkeypatch):
    import engine.synthesis as syn
    dirs = {name: tmp_path/name for name in ["referee","translations","money","power","barrel","left","right"]}
    _write_index(dirs["referee"]/"demo.json", "decisions", [_decision()])
    _write_index(dirs["translations"]/"demo.json", "translations", [{"anchor_id":"a1","status":"translated","plain_english":"The Secretary must establish the program.","confidence":0.95}])
    _write_index(dirs["money"]/"demo.json", "findings", [])
    _write_index(dirs["power"]/"demo.json", "findings", [])
    _write_index(dirs["barrel"]/"demo.json", "candidates", [])
    _write_index(dirs["left"]/"demo.json", "candidates", [{"anchor_id":"a1","confidence":0.86,"strongest_case_instruction":"Write a progressive case."}])
    _write_index(dirs["right"]/"demo.json", "candidates", [{"anchor_id":"a1","confidence":0.86,"strongest_case_instruction":"Write a conservative case."}])
    for attr, name in [("REFEREE_DIR","referee"),("TRANSLATION_DIR","translations"),("MONEY_DIR","money"),("POWER_DIR","power"),("BARREL_DIR","barrel"),("LEFT_DIR","left"),("RIGHT_DIR","right")]:
        monkeypatch.setattr(syn, attr, dirs[name])
    candidates = collect_candidates("demo")
    assert not any(c.claim.lens in {"LEFT","RIGHT"} for c in candidates)
    assert any(c.claim.lens == "TEXT" for c in candidates)


def test_collect_candidates_accepts_explicit_authored_advocacy(tmp_path, monkeypatch):
    import engine.synthesis as syn
    _mock_text_referee(monkeypatch, syn)
    dirs = {name: tmp_path/name for name in ["referee","translations","money","power","barrel","left","right"]}
    _write_index(dirs["referee"]/"demo.json", "decisions", [_decision()])
    _write_index(dirs["translations"]/"demo.json", "translations", [{"anchor_id":"a1","status":"translated","plain_english":"The Secretary must establish the program.","confidence":0.95}])
    for name, key in [("money","findings"),("power","findings"),("barrel","candidates")]:
        _write_index(dirs[name]/"demo.json", key, [])
    _write_index(dirs["left"]/"demo.json", "candidates", [{"anchor_id":"a1","confidence":0.86,"public_interpretation":"A progressive reading emphasizes access."}])
    _write_index(dirs["right"]/"demo.json", "candidates", [{"anchor_id":"a1","confidence":0.86,"public_interpretation":"A conservative reading emphasizes limits on delegated authority."}])
    for attr, name in [("REFEREE_DIR","referee"),("TRANSLATION_DIR","translations"),("MONEY_DIR","money"),("POWER_DIR","power"),("BARREL_DIR","barrel"),("LEFT_DIR","left"),("RIGHT_DIR","right")]:
        monkeypatch.setattr(syn, attr, dirs[name])
    candidates = collect_candidates("demo")
    lenses = {c.claim.lens for c in candidates if c.panel_key == "left_right_text"}
    assert lenses == {"LEFT", "RIGHT", "TEXT"}


def test_synthesize_bill_writes_public_analysis(tmp_path, monkeypatch):
    import engine.synthesis as syn
    monkeypatch.setattr(syn, "collect_candidates", lambda bill_id: _complete_candidates())
    monkeypatch.setattr(syn, "SYNTHESIS_DIR", tmp_path/"synthesis")
    monkeypatch.setattr(syn, "ANALYSIS_DIR", tmp_path/"analyses")
    result = synthesize_bill("demo")
    assert result.analysis_status == "verified"
    saved = json.loads((tmp_path/"analyses"/"demo.json").read_text())
    assert saved["analysis_status"] == "verified"
    assert len(saved["panels"]) == 5


def test_panel5_text_lane_can_use_bounded_translation_rejected_from_main_panel(tmp_path, monkeypatch):
    import engine.synthesis as syn
    _mock_text_referee(monkeypatch, syn)
    dirs = {name: tmp_path/name for name in ["referee","translations","money","power","barrel","left","right"]}
    _write_index(dirs["referee"]/"demo.json", "decisions", [_decision()])
    legalish = "The provision is amended to read as follows: the Secretary must establish the program and apply the stated eligibility rules."
    _write_index(dirs["translations"]/"demo.json", "translations", [{"anchor_id":"a1","status":"translated","plain_english":legalish,"confidence":0.95}])
    for name, key in [("money","findings"),("power","findings"),("barrel","candidates")]:
        _write_index(dirs[name]/"demo.json", key, [])
    _write_index(dirs["left"]/"demo.json", "candidates", [{"anchor_id":"a1","section_label":"SEC. 101.","confidence":0.86,"public_interpretation":"A progressive reading emphasizes access."}])
    _write_index(dirs["right"]/"demo.json", "candidates", [{"anchor_id":"a1","section_label":"SEC. 101.","confidence":0.86,"public_interpretation":"A conservative reading emphasizes limits."}])
    for attr, name in [("REFEREE_DIR","referee"),("TRANSLATION_DIR","translations"),("MONEY_DIR","money"),("POWER_DIR","power"),("BARREL_DIR","barrel"),("LEFT_DIR","left"),("RIGHT_DIR","right")]:
        monkeypatch.setattr(syn, attr, dirs[name])
    candidates = collect_candidates("demo")
    assert not any(c.panel_key == "what_it_really_does" for c in candidates)
    lenses = {c.claim.lens for c in candidates if c.panel_key == "left_right_text"}
    assert lenses == {"LEFT", "RIGHT", "TEXT"}
    analysis = assemble_analysis("demo", candidates)
    panel = next(p for p in analysis.panels if p.key == "left_right_text")
    assert [c.lens for c in panel.claims] == ["LEFT", "RIGHT", "TEXT"]


def test_lens_diagnostics_explain_missing_text_translation(tmp_path, monkeypatch):
    import engine.synthesis as syn
    _mock_text_referee(monkeypatch, syn)
    dirs = {name: tmp_path/name for name in ["referee","translations","left","right"]}
    _write_index(dirs["referee"]/"demo.json", "decisions", [_decision()])
    _write_index(dirs["translations"]/"demo.json", "translations", [{"anchor_id":"a1","status":"needs_expert_review","plain_english":None,"confidence":0.4}])
    _write_index(dirs["left"]/"demo.json", "candidates", [{"anchor_id":"a1","section_label":"SEC. 101.","public_interpretation":"A progressive reading emphasizes access."}])
    _write_index(dirs["right"]/"demo.json", "candidates", [{"anchor_id":"a1","section_label":"SEC. 101.","public_interpretation":"A conservative reading emphasizes limits."}])
    monkeypatch.setattr(syn, "REFEREE_DIR", dirs["referee"])
    monkeypatch.setattr(syn, "TRANSLATION_DIR", dirs["translations"])
    monkeypatch.setattr(syn, "LEFT_DIR", dirs["left"])
    monkeypatch.setattr(syn, "RIGHT_DIR", dirs["right"])
    diag = syn.diagnose_lens_surface("demo")
    assert diag["authored_pair_count"] == 1
    assert diag["complete_anchor_count"] == 1
    assert diag["anchors"][0]["text_referee_status"] == "constructed"
    assert diag["anchors"][0]["reasons"] == []

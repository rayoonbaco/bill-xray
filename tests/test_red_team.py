import json
from pathlib import Path

from engine import red_team


def _cite(anchor):
    return [{"bill_id":"demo","anchor_id":anchor,"section":"SEC. 1.","document_ref":"local:demo.txt","location_marker":"lines 1-2"}]


def _analysis(anchor="a1", money_anchor="m1", barrel_anchor="b1"):
    return {
        "bill_id":"demo","analysis_status":"verified","panels":[
            {"key":"what_it_really_does","title":"What It Really Does","claims":[{"text":"The Secretary must establish the program.","claim_class":"TEXT","confidence":.9,"citations":_cite(anchor),"lens":None}]},
            {"key":"follow_the_money","title":"Follow the Money","claims":[{"text":"The section appropriates $5 billion.","claim_class":"DIRECT_EFFECT","confidence":.9,"citations":_cite(money_anchor)}]},
            {"key":"barrel_scan","title":"Barrel Scan","claims":[{"text":"Narrow Carve-Out: The text creates a special rule for one recipient class.","claim_class":"DIRECT_EFFECT","confidence":.8,"citations":_cite(barrel_anchor),"barrel_label":"Narrow Carve-Out","why_flagged":"The text creates a special rule for one recipient class."}]},
            {"key":"who_wins_pays_power","title":"Who Wins / Who Pays / Who Gets Power","claims":[{"text":"The Secretary must issue implementing rules.","claim_class":"DIRECT_EFFECT","confidence":.9,"citations":_cite("p1")}]},
            {"key":"left_right_text","title":"Left | Right | Text","claims":[
                {"text":"A progressive reading emphasizes access and accountability.","claim_class":"INTERPRETATION","confidence":.8,"citations":_cite(anchor),"lens":"LEFT"},
                {"text":"A conservative reading emphasizes limits and local control.","claim_class":"INTERPRETATION","confidence":.8,"citations":_cite(anchor),"lens":"RIGHT"},
                {"text":"The Secretary must establish the program.","claim_class":"TEXT","confidence":.9,"citations":_cite(anchor),"lens":"TEXT"},
            ]},
        ]}


def _write(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _wire(tmp_path, monkeypatch, analysis):
    for name in ["analyses","money","barrel","red_team"]:
        setattr(red_team, {"analyses":"ANALYSIS_DIR","money":"MONEY_DIR","barrel":"BARREL_DIR","red_team":"RED_TEAM_DIR"}[name], tmp_path/name)
    _write(tmp_path/"analyses"/"demo.json", analysis)
    _write(tmp_path/"money"/"demo.json", {"findings":[{"anchor_id":"m1","amounts":[{"amount_usd":"5000000000"}]}]})
    _write(tmp_path/"barrel"/"demo.json", {"candidates":[{"anchor_id":"b1","factors":{"topical_distance":.8,"beneficiary_concentration":.78,"fiscal_significance":0,"scope_surprise":.65,"cross_reference_opacity":0,"narrow_carve_out":.5}}]})


def test_red_team_clean_report_passes(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch, _analysis())
    report = red_team.audit_analysis("demo")
    assert report.status == "pass"
    assert report.critical_count == 0


def test_red_team_blocks_misaligned_left_right_text(tmp_path, monkeypatch):
    analysis = _analysis()
    analysis["panels"][-1]["claims"][1]["citations"] = _cite("other")
    _wire(tmp_path, monkeypatch, analysis)
    report = red_team.audit_analysis("demo")
    assert report.status == "fail"
    assert any(f.code == "LENS_ANCHOR_MISMATCH" for f in report.findings)


def test_red_team_catches_trivial_money_selection(tmp_path, monkeypatch):
    analysis = _analysis(money_anchor="tiny")
    _wire(tmp_path, monkeypatch, analysis)
    _write(tmp_path/"money"/"demo.json", {"findings":[
        {"anchor_id":"tiny","status":"extracted","categories":["appropriation"],"operative_excerpt":"There is appropriated $500 for this program.","amounts":[{"amount_usd":"500"}]},
        {"anchor_id":"huge","status":"extracted","categories":["appropriation"],"operative_excerpt":"There is appropriated $50,000,000,000 for this program.","amounts":[{"amount_usd":"50000000000"}]},
    ]})
    report = red_team.audit_analysis("demo")
    assert any(f.code == "MONEY_SELECTION_TRIVIALIZED" for f in report.findings)


def test_red_team_rejects_lexical_only_barrel_rationale(tmp_path, monkeypatch):
    analysis = _analysis()
    analysis["panels"][2]["claims"][0]["text"] = "Potential Rider: Section-heading terms are lexically distant."
    analysis["panels"][2]["claims"][0]["why_flagged"] = "Section-heading terms are lexically distant."
    _wire(tmp_path, monkeypatch, analysis)
    _write(tmp_path/"barrel"/"demo.json", {"candidates":[{"anchor_id":"b1","factors":{"topical_distance":1.0,"beneficiary_concentration":0,"fiscal_significance":0,"scope_surprise":.4,"cross_reference_opacity":0,"narrow_carve_out":0}}]})
    report = red_team.audit_analysis("demo")
    assert any(f.code == "BARREL_WEAK_SIGNAL" for f in report.findings)


def test_red_team_catches_political_language_outside_advocacy(tmp_path, monkeypatch):
    analysis = _analysis()
    analysis["panels"][0]["claims"][0]["text"] = "A conservative policy requires the Secretary to act."
    _wire(tmp_path, monkeypatch, analysis)
    report = red_team.audit_analysis("demo")
    assert any(f.code == "POLITICAL_LANGUAGE_LEAK" for f in report.findings)


def test_synthesis_panel_five_uses_one_common_anchor():
    from engine.schemas import Citation, Claim
    from engine.synthesis import Candidate, assemble_analysis
    def c(lens, anchor, score):
        cite=Citation(bill_id="demo",anchor_id=anchor,section="SEC. 1.",document_ref="local:x",location_marker="lines 1-2")
        cls="TEXT" if lens=="TEXT" else "INTERPRETATION"
        return Candidate("left_right_text",Claim(text=f"{lens} {anchor}",claim_class=cls,confidence=.9,citations=[cite],lens=lens),score,anchor,"fixture")
    base=[]
    # Required first panel claim.
    cite=Citation(bill_id="demo",anchor_id="a",section="SEC. 1.",document_ref="local:x",location_marker="lines 1-2")
    base.append(Candidate("what_it_really_does",Claim(text="Effect.",claim_class="TEXT",confidence=.9,citations=[cite]),1,"a","fixture"))
    base += [c("LEFT","a",5),c("RIGHT","a",4),c("TEXT","a",3),c("TEXT","z",99)]
    analysis=assemble_analysis("demo",base)
    lens=analysis.panels[-1].claims
    assert [_anchor(c.model_dump()) for c in lens] == ["a","a","a"]


def _anchor(claim):
    return claim["citations"][0]["anchor_id"]


def test_red_team_ignores_giant_unclassified_context_amount_for_materiality(tmp_path, monkeypatch):
    analysis = _analysis(money_anchor="real")
    _wire(tmp_path, monkeypatch, analysis)
    _write(tmp_path/"money"/"demo.json", {"findings":[
        {"anchor_id":"projection","status":"needs_fiscal_context","categories":["unclassified_money_amount"],"amounts":[{"amount_usd":"4700000000000"}]},
        {"anchor_id":"real","status":"extracted","categories":["appropriation"],"amounts":[{"amount_usd":"5000000000"}]},
    ]})
    report = red_team.audit_analysis("demo")
    assert not any(f.code == "MONEY_SELECTION_TRIVIALIZED" for f in report.findings)


def test_red_team_does_not_compare_unlike_fiscal_classes(tmp_path, monkeypatch):
    analysis = _analysis(money_anchor="grant")
    _wire(tmp_path, monkeypatch, analysis)
    _write(tmp_path/"money"/"demo.json", {"findings":[
        {"anchor_id":"grant","status":"extracted","categories":["grant"],"operative_excerpt":"The Secretary shall award $500,000,000 in grants to eligible States.","amounts":[{"amount_usd":"500000000"}]},
        {"anchor_id":"projection","status":"extracted","categories":["revenue"],"operative_excerpt":"National revenue was projected to reach $5,000,000,000,000 under prior law.","amounts":[{"amount_usd":"5000000000000"}]},
    ]})
    report = red_team.audit_analysis("demo")
    assert not any(f.code == "MONEY_SELECTION_TRIVIALIZED" for f in report.findings)

def test_shared_materiality_marks_contextual_revenue_as_non_actionable():
    from engine import fiscal_materiality
    item={"status":"extracted","categories":["revenue"],"operative_excerpt":"National revenue was projected to reach $5,000,000,000,000 under prior law.","amounts":[{"amount_usd":"5000000000000"}]}
    assert fiscal_materiality.assess(item).actionable is False

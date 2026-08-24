import json
from pathlib import Path
from engine import red_team

ROOT = Path(__file__).resolve().parents[1]


def _cite(anchor):
    return [{"bill_id":"demo","anchor_id":anchor,"section":"SEC. 1.","document_ref":"local:demo.txt","location_marker":"lines 1-2"}]


def test_page2_leads_with_scrutiny_revelation_and_progressive_disclosure():
    html=(ROOT/'templates'/'bill.html').read_text(encoding='utf-8')
    assert 'These are the 3 things that most deserve your attention.' in html
    assert 'Why Bill X-Ray flagged it:' in html
    assert 'Could there be a normal explanation?' in html
    assert 'See the evidence →' in html
    assert 'Where does the money go?' in html
    assert 'Who benefits, who pays, who gets power?' in html
    assert '<details class="pass293-deeper">' in html
    assert '<details class="deep-dive">' in html


def test_money_hold_diagnostic_prints_exact_same_class_comparison(tmp_path, monkeypatch):
    analysis={"bill_id":"demo","analysis_status":"verified","panels":[
        {"key":"what_it_really_does","title":"What You Should Know","claims":[{"text":"The Secretary must act.","claim_class":"TEXT","confidence":.9,"citations":_cite('a')}]},
        {"key":"follow_the_money","title":"Follow the Money","claims":[{"text":"A $100 million tax applies.","claim_class":"DIRECT_EFFECT","confidence":.9,"citations":_cite('small')}]},
        {"key":"barrel_scan","title":"What Deserves Scrutiny","claims":[]},
        {"key":"who_wins_pays_power","title":"People & Power","claims":[]},
        {"key":"left_right_text","title":"Left | Right | Text","claims":[
            {"text":"Left.","claim_class":"INTERPRETATION","confidence":.8,"citations":_cite('a'),"lens":"LEFT"},
            {"text":"Right.","claim_class":"INTERPRETATION","confidence":.8,"citations":_cite('a'),"lens":"RIGHT"},
            {"text":"Text.","claim_class":"TEXT","confidence":.9,"citations":_cite('a'),"lens":"TEXT"},
        ]}
    ]}
    for attr,name in [('ANALYSIS_DIR','analyses'),('MONEY_DIR','money'),('BARREL_DIR','barrel'),('RED_TEAM_DIR','red_team')]:
        d=tmp_path/name; d.mkdir(parents=True,exist_ok=True); monkeypatch.setattr(red_team,attr,d)
    (tmp_path/'analyses'/'demo.json').write_text(json.dumps(analysis),encoding='utf-8')
    money={"findings":[
        {"anchor_id":"small","section_label":"SEC. 10","status":"extracted","categories":["tax"],"operative_excerpt":"A tax of $100,000,000 is imposed.","amounts":[{"amount_usd":"100000000"}]},
        {"anchor_id":"huge","section_label":"SEC. 90","status":"extracted","categories":["tax"],"operative_excerpt":"A tax of $5,000,000,000 is imposed.","amounts":[{"amount_usd":"5000000000"}]},
    ]}
    (tmp_path/'money'/'demo.json').write_text(json.dumps(money),encoding='utf-8')
    (tmp_path/'barrel'/'demo.json').write_text(json.dumps({"candidates":[]}),encoding='utf-8')
    report=red_team.audit_analysis('demo')
    hit=next(f for f in report.findings if f.code=='MONEY_SELECTION_TRIVIALIZED')
    assert 'PUBLISHED:' in hit.message
    assert 'SEC. 10' in hit.message
    assert '$100,000,000' in hit.message
    assert 'OMITTED LARGER:' in hit.message
    assert 'SEC. 90' in hit.message
    assert '$5,000,000,000' in hit.message
    assert 'class=revenue_tax' in hit.message
    assert 'RATIO=50.0x' in hit.message


def test_pass293_version_markers():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    launcher=(ROOT/'START_BILL_XRAY.bat').read_text(encoding='utf-8')
    bill=(ROOT/'templates'/'bill.html').read_text(encoding='utf-8')
    assert '"build_pass": "31"' in app
    assert 'PASS 31' in launcher
    assert 'style.css?v=31' in bill

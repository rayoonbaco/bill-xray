import json
from pathlib import Path

from engine import audit


def _write(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _citation(anchor="a1"):
    return {"bill_id":"demo","anchor_id":anchor,"section":"SEC. 1","document_ref":"local:demo.txt","location_marker":"canonical lines 1-2"}


def _claim(text, cls="TEXT", anchor="a1", lens=None):
    return {"text":text,"claim_class":cls,"confidence":.9,"citations":[_citation(anchor)],"lens":lens}


def _wire(tmp_path, monkeypatch, *, public_text="The Secretary must establish the program."):
    monkeypatch.setattr(audit, "ANALYSIS_DIR", tmp_path/"analyses")
    monkeypatch.setattr(audit, "TRANSLATION_DIR", tmp_path/"translations")
    monkeypatch.setattr(audit, "MONEY_DIR", tmp_path/"money")
    monkeypatch.setattr(audit, "POWER_DIR", tmp_path/"power")
    monkeypatch.setattr(audit, "BARREL_DIR", tmp_path/"barrel")
    monkeypatch.setattr(audit, "LEFT_DIR", tmp_path/"left")
    monkeypatch.setattr(audit, "RIGHT_DIR", tmp_path/"right")
    monkeypatch.setattr(audit, "AUDIT_DIR", tmp_path/"audit")
    analysis={"bill_id":"demo","analysis_status":"verified","panels":[
      {"key":"what_it_really_does","title":"What It Really Does","claims":[_claim(public_text)]},
      {"key":"follow_the_money","title":"Follow the Money","claims":[]},
      {"key":"barrel_scan","title":"Barrel Scan","claims":[]},
      {"key":"who_wins_pays_power","title":"Who Wins / Who Pays / Who Gets Power","claims":[]},
      {"key":"left_right_text","title":"Left | Right | Text","claims":[
        _claim("A progressive reading emphasizes access.","INTERPRETATION",lens="LEFT"),
        _claim("A conservative reading emphasizes limits.","INTERPRETATION",lens="RIGHT"),
        _claim(public_text,"TEXT",lens="TEXT"),
      ]},
    ]}
    _write(tmp_path/"analyses"/"demo.json",analysis)
    _write(tmp_path/"translations"/"demo.json",{"translations":[{"anchor_id":"a1","status":"translated","plain_english":public_text,"confidence":.9}]})
    _write(tmp_path/"left"/"demo.json",{"candidates":[{"anchor_id":"a1","public_interpretation":"A progressive reading emphasizes access."}]})
    _write(tmp_path/"right"/"demo.json",{"candidates":[{"anchor_id":"a1","public_interpretation":"A conservative reading emphasizes limits."}]})
    resolved={"bill_id":"demo","anchor_id":"a1","section_label":"SEC. 1","document_ref":"local:demo.txt","location_marker":"canonical lines 1-2","source_url":"","exact_text":"SEC. 1. The Secretary must establish the program.","source_sha256":"sha","text_sha256":"textsha"}
    monkeypatch.setattr(audit,"resolve_anchor",lambda bill_id,anchor_id:resolved)
    from types import SimpleNamespace
    monkeypatch.setattr(audit.text_referee, "construct_text_referee", lambda bill_id, anchor_id: SimpleNamespace(text=public_text))


def test_clean_public_report_reverifies_and_reproduces_every_claim(tmp_path, monkeypatch):
    _wire(tmp_path,monkeypatch)
    report=audit.audit_bill("demo")
    assert report.status == "pass"
    assert report.citations_checked == 4
    assert report.upstream_claims_reproduced == 4
    assert report.checks["all_public_text_reproducible"] is True


def test_audit_blocks_public_wording_that_cannot_be_reproduced(tmp_path, monkeypatch):
    _wire(tmp_path,monkeypatch,public_text="The Secretary must establish the program.")
    payload=json.loads((tmp_path/"analyses"/"demo.json").read_text())
    payload["panels"][0]["claims"][0]["text"]="The Secretary must abolish the program."
    _write(tmp_path/"analyses"/"demo.json",payload)
    report=audit.audit_bill("demo")
    assert report.status == "fail"
    assert any(f.code == "PUBLIC_TEXT_NOT_REPRODUCIBLE" for f in report.findings)


def test_audit_blocks_novel_number_in_factual_claim(tmp_path, monkeypatch):
    text="The program provides $999 million."
    _wire(tmp_path,monkeypatch,public_text=text)
    report=audit.audit_bill("demo")
    assert report.status == "fail"
    assert any(f.code == "NOVEL_NUMBER" for f in report.findings)


def test_audit_blocks_citation_metadata_drift(tmp_path, monkeypatch):
    _wire(tmp_path,monkeypatch)
    payload=json.loads((tmp_path/"analyses"/"demo.json").read_text())
    payload["panels"][0]["claims"][0]["citations"][0]["location_marker"]="canonical lines 99-100"
    _write(tmp_path/"analyses"/"demo.json",payload)
    report=audit.audit_bill("demo")
    assert any(f.code == "CITATION_METADATA_DRIFT" for f in report.findings)


def test_numeric_audit_accepts_money_spacing_format_variation(tmp_path, monkeypatch):
    text="The program provides $999 million."
    _wire(tmp_path,monkeypatch,public_text=text)
    resolved={"bill_id":"demo","anchor_id":"a1","section_label":"SEC. 1","document_ref":"local:demo.txt","location_marker":"canonical lines 1-2","source_url":"","exact_text":"SEC. 1. The program provides $ 999 million.","source_sha256":"sha","text_sha256":"textsha"}
    monkeypatch.setattr(audit,"resolve_anchor",lambda bill_id,anchor_id:resolved)
    report=audit.audit_bill("demo")
    assert not any(f.code == "NOVEL_NUMBER" for f in report.findings)


def test_numeric_audit_accepts_percent_word_format_variation(tmp_path, monkeypatch):
    text="The rate is 10%."
    _wire(tmp_path,monkeypatch,public_text=text)
    resolved={"bill_id":"demo","anchor_id":"a1","section_label":"SEC. 1","document_ref":"local:demo.txt","location_marker":"canonical lines 1-2","source_url":"","exact_text":"SEC. 1. The rate is 10 percent.","source_sha256":"sha","text_sha256":"textsha"}
    monkeypatch.setattr(audit,"resolve_anchor",lambda bill_id,anchor_id:resolved)
    report=audit.audit_bill("demo")
    assert not any(f.code == "NOVEL_NUMBER" for f in report.findings)


def test_numeric_audit_preserves_semantic_type(tmp_path, monkeypatch):
    text="The program provides $10."
    _wire(tmp_path,monkeypatch,public_text=text)
    resolved={"bill_id":"demo","anchor_id":"a1","section_label":"SEC. 1","document_ref":"local:demo.txt","location_marker":"canonical lines 1-2","source_url":"","exact_text":"SEC. 1. The program has 10 participants.","source_sha256":"sha","text_sha256":"textsha"}
    monkeypatch.setattr(audit,"resolve_anchor",lambda bill_id,anchor_id:resolved)
    report=audit.audit_bill("demo")
    assert any(f.code == "NOVEL_NUMBER" for f in report.findings)


def test_audit_reproduces_deliberate_synthesis_lens_bounding(tmp_path, monkeypatch):
    long_left = (
        "A progressive reading would focus on this concrete change: "
        + "The Attorney General shall issue rules to implement this Act. " * 8
        + "Its strongest question is public accountability and equal treatment."
    )
    long_right = (
        "A conservative reading would focus on the same concrete change: "
        + "The Attorney General shall issue rules to implement this Act. " * 8
        + "Its strongest question is whether the authority stays within clear legal limits."
    )
    _wire(tmp_path, monkeypatch)
    payload = json.loads((tmp_path/"analyses"/"demo.json").read_text())
    left_claim = payload["panels"][4]["claims"][0]
    right_claim = payload["panels"][4]["claims"][1]
    left_claim["text"] = audit.synthesis._clean(long_left)
    right_claim["text"] = audit.synthesis._clean(long_right)
    _write(tmp_path/"analyses"/"demo.json", payload)
    _write(tmp_path/"left"/"demo.json", {"candidates":[{"anchor_id":"a1","public_interpretation":long_left}]})
    _write(tmp_path/"right"/"demo.json", {"candidates":[{"anchor_id":"a1","public_interpretation":long_right}]})

    report = audit.audit_bill("demo")
    assert report.status == "pass"
    assert not any(f.code == "PUBLIC_TEXT_NOT_REPRODUCIBLE" for f in report.findings)


def test_audit_still_blocks_drift_after_synthesis_lens_bounding(tmp_path, monkeypatch):
    long_left = "A progressive reading would focus on this concrete change: " + ("source-bound effect. " * 30)
    _wire(tmp_path, monkeypatch)
    payload = json.loads((tmp_path/"analyses"/"demo.json").read_text())
    public = audit.synthesis._clean(long_left)
    payload["panels"][4]["claims"][0]["text"] = public[:-1] + "X"
    _write(tmp_path/"analyses"/"demo.json", payload)
    _write(tmp_path/"left"/"demo.json", {"candidates":[{"anchor_id":"a1","public_interpretation":long_left}]})

    report = audit.audit_bill("demo")
    assert report.status == "fail"
    assert any(f.code == "PUBLIC_TEXT_NOT_REPRODUCIBLE" for f in report.findings)


def test_pass32_1_public_clip_never_creates_partial_money_token():
    text = (
        "Congress provides or sets $25,000,000 for any taxable year if the average annual gross receipts "
        "of such entity for the 3-taxable-year period ending with the taxable year which precedes such "
        "taxable year does not exceed $25,000,000."
    )
    clipped = audit.so_what._clip(text, len(text) - 8)
    assert "$2…" not in clipped
    assert clipped.endswith("…")
    assert audit._numeric_signatures(clipped) <= audit._numeric_signatures(text)


def test_pass32_1_numeric_auditor_still_blocks_complete_novel_money(tmp_path, monkeypatch):
    text = "The program provides $10."
    _wire(tmp_path, monkeypatch, public_text=text)
    resolved={"bill_id":"demo","anchor_id":"a1","section_label":"SEC. 1","document_ref":"local:demo.txt","location_marker":"canonical lines 1-2","source_url":"","exact_text":"SEC. 1. The program provides $20.","source_sha256":"sha","text_sha256":"textsha"}
    monkeypatch.setattr(audit,"resolve_anchor",lambda bill_id,anchor_id:resolved)
    report=audit.audit_bill("demo")
    assert report.status == "fail"
    assert any(f.code == "NOVEL_NUMBER" for f in report.findings)

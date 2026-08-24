import json
from pathlib import Path

from engine import external_evidence, consequence


def test_official_search_keeps_only_official_relevant_links(monkeypatch):
    html = '''<html><a href="/publication/99999">H.R. 1 Cost Estimate</a><a href="https://example.com/x">H.R. 1 fake</a><a href="/about">About CBO</a></html>'''
    monkeypatch.setattr(external_evidence, "_get", lambda url: html)
    row = external_evidence._official_search("CBO", external_evidence.CBO_SEARCH, "H.R. 1", ("cbo.gov", "www.cbo.gov"))
    assert row["status"] == "found"
    assert len(row["results"]) == 1
    assert row["results"][0]["url"].startswith("https://www.cbo.gov/")


def test_usaspending_is_explicitly_noncausal(monkeypatch):
    monkeypatch.setattr(external_evidence, "_post_json", lambda u,p: {"results":[{"time_period":{"fiscal_year":"2025"},"aggregated_amount":1250000}]})
    row = external_evidence._usaspending_context({"year":2025,"implementation_keyword":"Example Health Program"})
    assert row["status"] == "found"
    assert row["total_related_obligations"] == 1250000
    assert "not proof" in row["note"].lower()


def test_external_network_failure_fails_open_as_context_not_release(monkeypatch, tmp_path):
    monkeypatch.setattr(external_evidence, "ROOT", tmp_path)
    monkeypatch.setattr(external_evidence, "OUT_DIR", tmp_path / "external")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "bills.json").write_text(json.dumps([{"id":"aca","short_title":"Affordable Care Act","year":2010}]))
    monkeypatch.setattr(external_evidence, "_get", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr(external_evidence, "_post_json", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    payload = external_evidence.collect_external_evidence("aca")
    assert payload["lanes"]["cbo"]["status"] == "unavailable"
    assert payload["lanes"]["jct"]["status"] == "unavailable"
    assert payload["lanes"]["usaspending"]["status"] == "unavailable"
    assert (external_evidence.OUT_DIR / "aca.json").exists()


def test_consequence_score_is_coverage_not_corruption(monkeypatch, tmp_path):
    monkeypatch.setattr(consequence, "ROOT", tmp_path)
    monkeypatch.setattr(consequence, "OUT_DIR", tmp_path / "consequence")
    for d in ["analyses","external_evidence","money","barrel_scan"]: (tmp_path/"data"/d).mkdir(parents=True, exist_ok=True)
    (tmp_path/"data"/"analyses"/"x.json").write_text(json.dumps({"panels":[{"claims":[1,2]}]}))
    (tmp_path/"data"/"external_evidence"/"x.json").write_text(json.dumps({"lanes":{"cbo":{"status":"found"},"jct":{"status":"no_match"},"usaspending":{"status":"found"}}}))
    (tmp_path/"data"/"money"/"x.json").write_text(json.dumps({"findings":[{"status":"finding"}]*4}))
    (tmp_path/"data"/"barrel_scan"/"x.json").write_text(json.dumps({"candidates":[{"candidate_score":.8}]}))
    payload=consequence.build_consequence_context("x")
    assert 0 < payload["consequence_confidence"] <= 1
    assert "not corruption" in payload["guardrail"].lower()


def test_pass30_public_surface_keeps_external_context_separate():
    html=Path("templates/bill.html").read_text(encoding="utf-8")
    index=Path("templates/index.html").read_text(encoding="utf-8")
    js=Path("static/build_controls.js").read_text(encoding="utf-8")
    assert "OUTSIDE THE BILL · OFFICIAL CONTEXT" in html
    assert "Three lanes, never blended" in html
    assert "CBO" in html and "JCT" in html and "USASPENDING" in html
    assert "CURATED PUBLIC EXHIBITS" in index
    assert "['external'" in js and "['consequence'" in js


def test_cbo_bill_number_normalization_supports_predictable_urls():
    assert external_evidence._normalize_bill_number("H.R. 3590") == {"chamber":"hr","number":"3590","canonical":"H.R. 3590"}
    assert external_evidence._normalize_bill_number("S. 2302")["chamber"] == "s"
    assert external_evidence._normalize_bill_number("not a bill") is None


def test_cbo_predictable_bill_page_finds_aca_and_rejects_wrong_same_number(monkeypatch):
    page = '''<html>
    <a href="/publication/21279">H.R. 3590, Patient Protection and Affordable Care Act</a>
    <a href="/publication/99991">H.R. 3590, Halt Tax Increases on the Middle Class and Seniors Act</a>
    </html>'''
    xml = '<rss><channel></channel></rss>'
    def fake_get(url, *args, **kwargs):
        if '/cost-estimates/hr/3590' in url: return page
        if '111congress-cost-estimates.xml' in url: return xml
        return '<html></html>'
    monkeypatch.setattr(external_evidence, '_get', fake_get)
    row = external_evidence._cbo_discovery({"bill_number":"H.R. 3590","official_title":"Patient Protection and Affordable Care Act","short_title":"Affordable Care Act","congress":111})
    assert row['status'] == 'found'
    assert row['selected']['url'].endswith('/publication/21279')
    assert row['selected']['identity_confidence'] >= .8
    assert all('Halt Tax' not in r['title'] for r in row['results'])


def test_cbo_congress_xml_is_a_second_official_discovery_path(monkeypatch):
    xml = '''<rss><channel><item>
      <title>H.R. 1, One Big Beautiful Bill Act (Dynamic Estimate)</title>
      <link>https://www.cbo.gov/publication/61486</link><pubDate>June 17, 2025</pubDate>
    </item></channel></rss>'''
    def fake_get(url, *args, **kwargs):
        if '/cost-estimates/hr/1' in url: raise OSError('blocked')
        if '119congress-cost-estimates.xml' in url: return xml
        return '<html></html>'
    monkeypatch.setattr(external_evidence, '_get', fake_get)
    row = external_evidence._cbo_discovery({"bill_number":"H.R. 1","short_title":"One Big Beautiful Bill Act","congress":119})
    assert row['status'] == 'found'
    assert row['selected']['url'].endswith('/publication/61486')
    assert any(d['method'] == 'congress_xml' and d['status'] == 'ok' for d in row['diagnostics'])


def test_cbo_ambiguous_or_wrong_title_is_not_force_attached(monkeypatch):
    page = '<html><a href="/publication/53312">H.R. 1, the Tax Cuts and Jobs Act</a></html>'
    monkeypatch.setattr(external_evidence, '_get', lambda url, *a, **k: page if '/cost-estimates/hr/1' in url else '<rss><channel></channel></rss>')
    row = external_evidence._cbo_discovery({"bill_number":"H.R. 1","short_title":"One Big Beautiful Bill Act","congress":119})
    # Exact bill number alone is not enough when a title is available and conflicts.
    assert row['status'] in {'no_match','unavailable'}
    assert not row['results']


def test_cbo_network_failure_remains_honest_and_fail_open(monkeypatch):
    monkeypatch.setattr(external_evidence, '_get', lambda *a, **k: (_ for _ in ()).throw(OSError('offline')))
    row = external_evidence._cbo_discovery({"bill_number":"H.R. 3590","official_title":"Patient Protection and Affordable Care Act","short_title":"Affordable Care Act","congress":111})
    assert row['status'] == 'unavailable'
    assert 'not evidence' in row['note'].lower()


def test_cbo_public_surface_names_selected_official_document():
    html = Path('templates/bill.html').read_text(encoding='utf-8')
    assert "cbo_selected.get('title')" in html
    assert 'CBO context could not be verified automatically' in html

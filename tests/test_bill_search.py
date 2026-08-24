import io, json
from pathlib import Path
import engine.bill_search as bs

class FakeHeaders:
    def get_content_charset(self): return 'utf-8'
class FakeResponse:
    def __init__(self, payload): self.payload=payload; self.headers=FakeHeaders()
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def read(self): return json.dumps(self.payload).encode()

def test_search_normalizes_official_govinfo_results(monkeypatch, tmp_path):
    monkeypatch.setattr(bs, 'SEARCH_DIR', tmp_path/'search')
    payload={'results':[{'title':'H.R. 1 (ENR) - Example Act','packageId':'BILLS-119hr1enr','dateIssued':'2025-07-04'}]}
    monkeypatch.setattr(bs.urllib.request, 'urlopen', lambda *a,**k: FakeResponse(payload))
    out=bs.search_bills('H.R. 1')
    assert out['provider']=='GovInfo' and out['count']==1
    item=out['results'][0]
    assert item['bill_number']=='H.R. 1'
    assert item['version_label']=='Enrolled Bill'
    assert item['source_url'].endswith('/BILLS-119hr1enr.htm')
    assert (tmp_path/'search'/f"{out['search_token']}.json").exists()

def test_register_selected_bill_wires_dynamic_catalog_and_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(bs, 'SEARCH_DIR', tmp_path/'search')
    monkeypatch.setattr(bs, 'DYNAMIC_CATALOG', tmp_path/'dynamic_bills.json')
    monkeypatch.setattr(bs, 'SOURCE_MANIFEST', tmp_path/'source_manifest.json')
    bs._write_json(bs.SOURCE_MANIFEST, {'schema_version':'2.0','bills':[]})
    token='a'*18
    item=bs._normalize_result({'title':'H.R. 6570 (RH) - Protect Liberty Act','packageId':'BILLS-118hr6570rh','dateIssued':'2023-12-11'})
    bs._write_json(bs.SEARCH_DIR/f'{token}.json', {'query':'liberty','results':[item]})
    record=bs.register_selected_bill(token, 'BILLS-118hr6570rh')
    assert record['id']=='gpo-118hr6570rh'
    assert record['dynamic'] is True
    manifest=json.loads(bs.SOURCE_MANIFEST.read_text())
    assert manifest['bills'][0]['package_id']=='BILLS-118hr6570rh'
    assert manifest['bills'][0]['local_filename']=='gpo-118hr6570rh.txt'

def test_dynamic_html_text_rejects_tiny_download():
    try:
        bs.html_to_bill_text('<html><body>tiny</body></html>')
    except ValueError as exc:
        assert 'incomplete' in str(exc)
    else:
        raise AssertionError('expected incomplete bill rejection')

def test_exact_govinfo_package_id_bypasses_search_api(monkeypatch, tmp_path):
    monkeypatch.setattr(bs, 'SEARCH_DIR', tmp_path/'search')
    def network_must_not_run(*a, **k):
        raise AssertionError('exact package lookup must not call GovInfo Search API')
    monkeypatch.setattr(bs.urllib.request, 'urlopen', network_must_not_run)

    out = bs.search_bills('gpo-118hr171ih')

    assert out['provider'] == 'GovInfo exact package'
    assert out['count'] == 1
    item = out['results'][0]
    assert item['package_id'] == 'BILLS-118hr171ih'
    assert item['bill_number'] == 'H.R. 171'
    assert item['congress'] == 118
    assert item['version_code'] == 'ih'
    assert item['source_url'].endswith('/BILLS-118hr171ih.htm')
    assert (tmp_path/'search'/f"{out['search_token']}.json").exists()


def test_exact_bills_package_id_bypasses_search_api(monkeypatch, tmp_path):
    monkeypatch.setattr(bs, 'SEARCH_DIR', tmp_path/'search')
    monkeypatch.setattr(bs.urllib.request, 'urlopen', lambda *a, **k: (_ for _ in ()).throw(AssertionError('network called')))
    out = bs.search_bills('BILLS-118hr171ih')
    assert out['results'][0]['package_id'] == 'BILLS-118hr171ih'

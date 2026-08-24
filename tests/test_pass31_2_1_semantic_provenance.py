import json
from pathlib import Path

from engine import audit, human_consequence, semantic_roles, so_what


def _anchor_dir(tmp_path: Path):
    d = tmp_path / "citation_anchors"
    d.mkdir(parents=True, exist_ok=True)
    (d / "demo.json").write_text(json.dumps({"anchors": [
        {"anchor_id": "a1", "kind": "section", "identifier": "100", "heading": "SEC. 100. TEMPORARY REINSURANCE PROGRAM", "excerpt": "SEC. 100"}
    ]}), encoding="utf-8")
    return d


def test_main_effect_uses_same_semantic_public_text_as_audit_path(monkeypatch, tmp_path):
    monkeypatch.setattr(semantic_roles, "ANCHOR_DIR", _anchor_dir(tmp_path))
    money = {
        "bill_id": "demo", "anchor_id": "a1", "status": "extracted",
        "categories": ["appropriation"], "fiscal_direction": "funding_or_authority",
        "timing": ["fiscal year 2014"], "confidence": .98,
        "operative_excerpt": "For fiscal year 2014, $19,147,000,000 is appropriated.",
        "amounts": [{"raw": "$19,147,000,000", "amount_usd": "19147000000", "context_excerpt": "For fiscal year 2014, $19,147,000,000 is appropriated.", "context_kind": "statutory_clause", "local_categories": ["appropriation"]}],
    }
    text, why, kind = so_what.main_effect_from_findings(money, None)
    canonical, canonical_why = so_what.money_explanation(money)
    assert kind == "money"
    assert text == canonical
    assert why == canonical_why
    assert "TEMPORARY REINSURANCE PROGRAM" in text


def test_audit_blocks_semantic_role_metadata_drift(monkeypatch):
    indexes = {"money": {"a1": {}}, "power": {"a1": {}}}
    monkeypatch.setattr(human_consequence, "money_fields", lambda finding: {"semantic_actor": "Congress", "semantic_period": "fiscal year 2014"})
    expected = audit._semantic_expected("follow_the_money", "a1", indexes)
    assert expected["semantic_actor"] == "Congress"
    public = audit._semantic_public_fields({"semantic_actor": "the Secretary", "semantic_period": "fiscal year 2014"})
    assert audit._normalize(public["semantic_actor"]) != audit._normalize(expected["semantic_actor"])


def test_audit_semantic_fields_are_ignored_when_not_published():
    assert audit._semantic_public_fields({"text": "source-bound claim"}) == {}

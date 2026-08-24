from engine import audit, human_consequence
from engine.schemas import Claim, Citation


def _citation():
    return Citation(
        bill_id="demo",
        anchor_id="a1",
        section="SEC. 1",
        document_ref="local:/demo.txt",
        location_marker="lines 1-2",
    )


def test_core_claim_carries_semantic_source_kind():
    claim = Claim(
        text="The Secretary must act.",
        claim_class="DIRECT_EFFECT",
        confidence=0.9,
        citations=[_citation()],
        semantic_actor="The Secretary",
        semantic_action="must act",
        semantic_source_kind="power",
    )
    assert claim.semantic_source_kind == "power"


def test_audit_regenerates_core_power_semantics_from_canonical_power(monkeypatch):
    canonical = {
        "authority_actor": "The Secretary of Health and Human Services",
        "authority_type": "mandatory duty",
        "authority_target": "a demonstration project",
        "affected_party": "a demonstration project",
        "semantic_actor": "The Secretary of Health and Human Services",
        "semantic_action": "must establish a demonstration project",
        "semantic_purpose": None,
        "semantic_period": None,
        "semantic_unknown": "The full effect depends on an unresolved cross-reference.",
        "missing_context": "The full effect depends on an unresolved cross-reference.",
    }
    monkeypatch.setattr(human_consequence, "power_fields", lambda finding: canonical)
    indexes = {"money": {"a1": {}}, "power": {"a1": {"anchor_id": "a1"}}}
    expected = audit._semantic_expected(
        "what_it_really_does",
        "a1",
        indexes,
        {"semantic_source_kind": "power"},
    )
    assert expected == canonical


def test_audit_regenerates_core_money_semantics_from_canonical_money(monkeypatch):
    canonical = {
        "fiscal_amount": "$5,000,000,000",
        "fiscal_mechanism": "funding or spending authority",
        "fiscal_recipient": None,
        "fiscal_purpose": "the medical expenses incurred by the program",
        "fiscal_period": "fiscal year 2014",
        "affected_party": None,
        "semantic_actor": "Congress",
        "semantic_action": "provides $5,000,000,000",
        "semantic_purpose": "the medical expenses incurred by the program",
        "semantic_period": "fiscal year 2014",
        "semantic_unknown": "The final recipient is not identifiable from this clause alone.",
        "missing_context": "The final recipient is not identifiable from this clause alone.",
    }
    monkeypatch.setattr(human_consequence, "money_fields", lambda finding: canonical)
    indexes = {"money": {"a1": {"anchor_id": "a1"}}, "power": {"a1": {}}}
    expected = audit._semantic_expected(
        "what_it_really_does",
        "a1",
        indexes,
        {"semantic_source_kind": "money"},
    )
    assert expected == canonical


def test_core_semantics_without_source_kind_fail_closed():
    indexes = {"money": {"a1": {}}, "power": {"a1": {}}}
    assert audit._semantic_expected("what_it_really_does", "a1", indexes, {}) == {}

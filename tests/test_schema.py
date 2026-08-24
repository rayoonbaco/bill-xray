import pytest
from pydantic import ValidationError
from engine.schemas import BillAnalysis, Claim, Citation, Panel


def citation():
    return Citation(
        bill_id="demo",
        anchor_id="bxr-demo-L1-L4-deadbeef",
        section="Sec. 1",
        document_ref="local:demo.txt",
        location_marker="lines 1-4",
        excerpt="The Secretary shall...",
    )


def claim(**overrides):
    data = dict(text="Demo claim", claim_class="TEXT", confidence=1.0, citations=[citation()])
    data.update(overrides)
    return Claim(**data)


def test_claim_requires_citation():
    with pytest.raises(ValidationError):
        Claim(text="Unsupported", claim_class="TEXT", confidence=1.0, citations=[])


def test_citation_requires_source_reference():
    with pytest.raises(ValidationError):
        Citation(bill_id="demo", section="Sec. 1", location_marker="lines 1-4")


def test_panel_maximum_three_claims():
    with pytest.raises(ValidationError):
        Panel(key="what_it_really_does", title="What It Really Does", claims=[claim(), claim(), claim(), claim()])


def test_barrel_flag_requires_reason():
    with pytest.raises(ValidationError):
        claim(barrel_label="Potential Rider")


def test_left_right_are_interpretation():
    with pytest.raises(ValidationError):
        claim(lens="LEFT", claim_class="TEXT")


def test_text_lens_is_not_interpretation():
    with pytest.raises(ValidationError):
        claim(lens="TEXT", claim_class="INTERPRETATION")


def test_verified_analysis_requires_five_panels_in_order():
    with pytest.raises(ValidationError):
        BillAnalysis(bill_id="demo", analysis_status="verified", panels=[])

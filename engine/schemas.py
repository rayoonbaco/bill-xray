from typing import Literal, List, Optional
from pydantic import BaseModel, Field, HttpUrl, model_validator

ClaimClass = Literal["TEXT", "DIRECT_EFFECT", "LIKELY_EFFECT", "INTERPRETATION", "DISPUTED", "UNKNOWN"]
PanelKey = Literal["what_it_really_does", "follow_the_money", "barrel_scan", "who_wins_pays_power", "left_right_text"]
BarrelLabel = Literal["Potential Rider", "Scope Surprise", "Narrow Carve-Out", "Highly Specific Beneficiary", "Cross-Reference Opacity"]
Lens = Literal["LEFT", "RIGHT", "TEXT"]

class Citation(BaseModel):
    bill_id: str = Field(min_length=1)
    anchor_id: Optional[str] = None
    title: Optional[str] = None
    section: str = Field(min_length=1)
    page: Optional[str] = None
    source_url: Optional[HttpUrl] = None
    document_ref: Optional[str] = None
    source_label: Optional[str] = None
    excerpt: Optional[str] = None
    location_marker: Optional[str] = None
    cross_reference_chain: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def source_and_location_are_traceable(self):
        if not (self.source_url or self.document_ref):
            raise ValueError("citation requires source_url or document_ref")
        if not (self.excerpt or self.location_marker):
            raise ValueError("citation requires excerpt or location_marker")
        return self

class Claim(BaseModel):
    text: str = Field(min_length=1)
    claim_class: ClaimClass
    confidence: float = Field(ge=0.0, le=1.0)
    citations: List[Citation] = Field(min_length=1)
    why_flagged: Optional[str] = None
    barrel_label: Optional[BarrelLabel] = None
    lens: Optional[Lens] = None
    direct_effect: Optional[bool] = None
    plain_explanation: Optional[str] = None
    why_it_matters: Optional[str] = None
    ordinary_explanation: Optional[str] = None
    scrutiny_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    # Pass 31 public consequence fields. These remain optional so historical artifacts
    # continue to validate, while new synthesis can expose human-readable fiscal/power detail.
    public_title: Optional[str] = None
    affected_party: Optional[str] = None
    fiscal_amount: Optional[str] = None
    fiscal_mechanism: Optional[str] = None
    fiscal_recipient: Optional[str] = None
    fiscal_purpose: Optional[str] = None
    fiscal_period: Optional[str] = None
    missing_context: Optional[str] = None
    authority_actor: Optional[str] = None
    authority_type: Optional[str] = None
    authority_target: Optional[str] = None
    # Pass 31.2 mutually-exclusive human semantic roles. These are display metadata,
    # never a substitute for the source-bound claim and citation.
    semantic_actor: Optional[str] = None
    semantic_action: Optional[str] = None
    semantic_purpose: Optional[str] = None
    semantic_period: Optional[str] = None
    semantic_unknown: Optional[str] = None
    # Pass 31.4.1 provenance handshake: identifies which canonical semantic object
    # supplied the published role metadata on CORE claims. This is metadata, not evidence.
    semantic_source_kind: Optional[Literal["money", "power"]] = None

    @model_validator(mode="after")
    def enforce_semantics(self):
        if self.barrel_label and not self.why_flagged:
            raise ValueError("Barrel Scan claims require why_flagged")
        if self.lens == "TEXT" and self.claim_class == "INTERPRETATION":
            raise ValueError("TEXT lens cannot contain INTERPRETATION claims")
        if self.lens in {"LEFT", "RIGHT"} and self.claim_class not in {"INTERPRETATION", "DISPUTED"}:
            raise ValueError("LEFT/RIGHT lens claims must be INTERPRETATION or DISPUTED")
        return self

class Panel(BaseModel):
    key: PanelKey
    title: str
    claims: List[Claim] = Field(max_length=3)

class BillAnalysis(BaseModel):
    bill_id: str
    analysis_status: Literal["not_generated", "draft", "verified", "rejected"]
    panels: List[Panel]

    @model_validator(mode="after")
    def verified_analysis_has_exact_surface(self):
        if self.analysis_status != "verified":
            return self
        required = ["what_it_really_does", "follow_the_money", "barrel_scan", "who_wins_pays_power", "left_right_text"]
        keys = [p.key for p in self.panels]
        if keys != required:
            raise ValueError("verified analysis must contain exactly the five panels in canonical order")
        if len(self.panels[0].claims) == 0:
            raise ValueError("verified analysis requires at least one What It Really Does claim")
        if any(not citation.anchor_id for panel in self.panels for claim in panel.claims for citation in claim.citations):
            raise ValueError("verified analysis citations must use Pass 4 anchor_id values")
        lens_panel = self.panels[-1]
        lenses = [claim.lens for claim in lens_panel.claims]
        if lenses != ["LEFT", "RIGHT", "TEXT"]:
            raise ValueError("verified LEFT | RIGHT | TEXT panel must contain exactly LEFT, RIGHT, TEXT in order")
        if lens_panel.claims[0].claim_class not in {"INTERPRETATION", "DISPUTED"}:
            raise ValueError("verified LEFT lane must remain interpretation/disputed")
        if lens_panel.claims[1].claim_class not in {"INTERPRETATION", "DISPUTED"}:
            raise ValueError("verified RIGHT lane must remain interpretation/disputed")
        if lens_panel.claims[2].claim_class == "INTERPRETATION":
            raise ValueError("verified TEXT lane cannot be interpretation")
        return self

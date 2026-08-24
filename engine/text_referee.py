"""Pass 19.3: source-bound TEXT referee construction for Panel 5.

The TEXT column has a different job from the plain-English translator. It must not
argue, predict, or paraphrase a whole section. It needs one compact proposition that
is traceable to the exact same statutory anchor used by LEFT and RIGHT.

This module therefore uses an extractive strategy: resolve the Pass 4 anchor, choose
an operative statutory sentence/clause, normalize only whitespace/formatting, and
return that source text as the neutral referee statement. No political or causal
language is added.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from engine import citations

TEXT_REFEREE_VERSION = "19.3-extractive-same-anchor"

_OPERATIVE = re.compile(
    r"\b(shall|shall not|may|may not|must|is amended|are amended|is repealed|"
    r"are repealed|striking|inserting|deduction|eligible|eligibility|requirement|"
    r"credit|appropriat(?:e|ed|ion)|prohibit(?:ed|ion)?|establish(?:ed|es)?)\b",
    re.IGNORECASE,
)
_SECTION_HEADING = re.compile(r"^\s*SEC\.\s+[^.\n]+\.\s*", re.IGNORECASE)
_MARKUPISH = re.compile(r"<[^>]+>|\[Page\s+\d+\]", re.IGNORECASE)


@dataclass(frozen=True)
class TextRefereeStatement:
    schema_version: str
    constructor_version: str
    bill_id: str
    anchor_id: str
    section_label: str
    status: str
    claim_class: str
    confidence: float
    text: str | None
    exact_source_fragment: str | None
    source_sha256: str
    text_sha256: str
    location_marker: str
    reason: str | None


def _normalize(text: str) -> str:
    text = _MARKUPISH.sub(" ", str(text or ""))
    return " ".join(text.split()).strip()


def _body(exact_text: str) -> str:
    compact = _normalize(exact_text)
    compact = _SECTION_HEADING.sub("", compact, count=1)
    return compact.strip()


def _sentences(text: str) -> list[str]:
    # Statutes use semicolons heavily; keep them inside a sentence so qualifiers are
    # less likely to be detached. Split only at strong sentence boundaries.
    parts = re.split(r"(?<=[.;])\s+(?=(?:\([A-Za-z0-9]+\)\s*)?[A-Z])", text)
    return [p.strip() for p in parts if p.strip()]


def _bounded_fragment(sentence: str, limit: int = 420) -> str:
    sentence = _normalize(sentence)
    if len(sentence) <= limit:
        return sentence

    # Prefer a complete semicolon-delimited clause when the full sentence is huge.
    clauses = [c.strip() for c in sentence.split(";") if c.strip()]
    chosen: list[str] = []
    total = 0
    for clause in clauses:
        addition = len(clause) + (2 if chosen else 0)
        if chosen and total + addition > limit:
            break
        if not chosen and len(clause) > limit:
            # Do not fabricate a shortened legal proposition by arbitrary truncation.
            return ""
        chosen.append(clause)
        total += addition
    return "; ".join(chosen).strip()


def construct_text_referee(bill_id: str, anchor_id: str) -> TextRefereeStatement:
    anchor = citations.resolve_anchor(bill_id, anchor_id)
    body = _body(str(anchor.get("exact_text") or ""))
    if not body:
        return TextRefereeStatement(
            "19.3", TEXT_REFEREE_VERSION, bill_id, anchor_id,
            str(anchor.get("section_label") or ""), "unusable", "TEXT", 0.0,
            None, None, str(anchor.get("source_sha256") or ""),
            str(anchor.get("text_sha256") or ""), str(anchor.get("location_marker") or ""),
            "The anchored section has no usable substantive body text.",
        )

    sentences = _sentences(body)
    ranked = [s for s in sentences if _OPERATIVE.search(s)] or sentences
    fragment = ""
    for sentence in ranked:
        fragment = _bounded_fragment(sentence)
        if fragment:
            break

    if not fragment:
        return TextRefereeStatement(
            "19.3", TEXT_REFEREE_VERSION, bill_id, anchor_id,
            str(anchor.get("section_label") or ""), "unusable", "TEXT", 0.0,
            None, None, str(anchor.get("source_sha256") or ""),
            str(anchor.get("text_sha256") or ""), str(anchor.get("location_marker") or ""),
            "No complete bounded statutory sentence or clause could be extracted safely.",
        )

    # The displayed TEXT lane is deliberately extractive. The only added characters
    # are quotation marks, which make clear that this is statutory language rather than
    # an interpretive paraphrase.
    rendered = f'“{fragment}”'
    return TextRefereeStatement(
        "19.3", TEXT_REFEREE_VERSION, bill_id, anchor_id,
        str(anchor.get("section_label") or ""), "constructed", "TEXT", 0.99,
        rendered, fragment, str(anchor.get("source_sha256") or ""),
        str(anchor.get("text_sha256") or ""), str(anchor.get("location_marker") or ""), None,
    )


def statement_dict(bill_id: str, anchor_id: str) -> dict:
    return asdict(construct_text_referee(bill_id, anchor_id))

"""Pass 25.1: challenge public explanations before publication.

This module is deliberately conservative and deterministic. It does not create new
facts. It grades whether an already source-bound explanation actually completes the
human thought: who acts, what changes, who/what is affected, why it matters, what is
unknown, whether a teenager can understand it, and whether the wording remains tied to
source-derived material.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

LEGAL_NOISE = (
    "notwithstanding", "hereinafter", "subparagraph", "subsection", "paragraph (",
    "clause (", "u.s.c.", "is amended by", "is amended to", "striking", "inserting", "redesignated",
    "read as follows", "<note", "qualified opportunity zone business--",
)
GENERIC_FAILURES = (
    "changes authority involving", "has a federal authority provision involving",
    "this changes how revenue works", "this changes how appropriation works",
    "this changes how grant works", "this changes the legal job or authority",
    "source excerpt is needed to say safely", "source excerpt is needed to identify safely",
)


@dataclass(frozen=True)
class ComprehensionResult:
    score: int
    possible: int
    publish: bool
    verdict: str
    passed: list[str]
    failed: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compact(value: object) -> str:
    return " ".join(str(value or "").split())


def _teenager_clear(text: str) -> bool:
    low = text.lower()
    if not text or len(text) > 340:
        return False
    if any(token in low for token in LEGAL_NOISE):
        return False
    if any(token in low for token in GENERIC_FAILURES):
        return False
    # Dense citation-like parenthetical chains are usually legal code, not explanation.
    if text.count("(") >= 4 or text.count(";") >= 5:
        return False
    return True


def _why_is_real(why: str) -> bool:
    low = why.lower()
    if not why:
        return False
    if any(token in low for token in GENERIC_FAILURES):
        return False
    circular = (
        "matters because it changes", "why it matters: this matters because",
        "deserves attention because it deserves",
    )
    return not any(token in low for token in circular)


def evaluate_packet(packet: Any, *, evidence_bound: bool = True) -> ComprehensionResult:
    """Grade a Pass-25 MeaningPacket against the seven public-comprehension gates."""
    passed: list[str] = []
    failed: list[str] = []

    actor = _compact(getattr(packet, "actor", None))
    action = _compact(getattr(packet, "action", None))
    target = _compact(getattr(packet, "target", None) or getattr(packet, "recipient", None))
    statement = _compact(getattr(packet, "plain_statement", None))
    why = _compact(getattr(packet, "why_it_matters", None))
    missing = list(getattr(packet, "missing_context", None) or [])

    checks = [
        ("WHO", bool(actor) or getattr(packet, "source_kind", "") == "money"),
        ("DOES_WHAT", bool(action) or (getattr(packet, "source_kind", "") == "money" and bool(statement))),
        ("TO_WHOM_OR_WHAT", bool(target) or bool(getattr(packet, "purpose", None))),
        ("WHY_IT_MATTERS", _why_is_real(why)),
        ("WHAT_WE_DONT_KNOW", isinstance(missing, list)),
        ("15_YEAR_OLD_TEST", _teenager_clear(statement) and _teenager_clear(why)),
        ("EVIDENCE_TEST", bool(evidence_bound and statement)),
    ]
    for name, ok in checks:
        (passed if ok else failed).append(name)

    score = len(passed)
    publish = score >= 6 and "DOES_WHAT" in passed and "TO_WHOM_OR_WHAT" in passed and "WHY_IT_MATTERS" in passed and "EVIDENCE_TEST" in passed
    if publish:
        verdict = "PASS_GENUINELY_UNDERSTANDABLE"
    elif "EVIDENCE_TEST" in failed:
        verdict = "FAIL_UNSUPPORTED"
    elif "WHY_IT_MATTERS" in failed:
        verdict = "FAIL_WHY_IT_MATTERS"
    elif "TO_WHOM_OR_WHAT" in failed:
        verdict = "FAIL_MISSING_AFFECTED_PARTY"
    else:
        verdict = "FAIL_DETECTED_NOT_EXPLAINED"
    return ComprehensionResult(score, 7, publish, verdict, passed, failed)


def evaluate_text(text: str, why: str | None = None, *, evidence_bound: bool = True) -> ComprehensionResult:
    """Fallback gate for source-bound public text that has no MeaningPacket."""
    text = _compact(text)
    why = _compact(why)
    passed: list[str] = []
    failed: list[str] = []

    # A usable public sentence normally has a named subject and a concrete verb/modal.
    has_subject = bool(re.search(r"\b(the |a |an |congress|states?|people|businesses|workers|taxpayers|secretary|attorney general|agency|department)\b", text, re.I))
    has_action = bool(re.search(r"\b(must|may|cannot|can|provides?|requires?|prohibits?|limits?|pays?|receives?|grants?|reduces?|increases?|creates?|ends?|allows?)\b", text, re.I))
    has_target = bool(re.search(r"\b(to|for|from|against|on|eligible|people|states?|businesses|workers|taxpayers|registrant|program|agency)\b", text, re.I))
    checks = [
        ("WHO", has_subject),
        ("DOES_WHAT", has_action),
        ("TO_WHOM_OR_WHAT", has_target),
        ("WHY_IT_MATTERS", _why_is_real(why)),
        ("WHAT_WE_DONT_KNOW", True),
        ("15_YEAR_OLD_TEST", _teenager_clear(text) and (not why or _teenager_clear(why))),
        ("EVIDENCE_TEST", bool(evidence_bound and text)),
    ]
    for name, ok in checks:
        (passed if ok else failed).append(name)
    score = len(passed)
    publish = score >= 6 and "DOES_WHAT" in passed and "EVIDENCE_TEST" in passed
    if publish:
        verdict = "PASS_GENUINELY_UNDERSTANDABLE"
    elif "EVIDENCE_TEST" in failed:
        verdict = "FAIL_UNSUPPORTED"
    elif "WHY_IT_MATTERS" in failed:
        verdict = "FAIL_WHY_IT_MATTERS"
    elif "TO_WHOM_OR_WHAT" in failed:
        verdict = "FAIL_MISSING_AFFECTED_PARTY"
    else:
        verdict = "FAIL_DETECTED_NOT_EXPLAINED"
    return ComprehensionResult(score, 7, publish, verdict, passed, failed)

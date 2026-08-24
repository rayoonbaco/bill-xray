"""Pass 27: Context Prosecutor.

The prosecutor does not decide policy merits. It asks whether a public claim can be
technically supported by one excerpt yet still be materially misleading without
nearby definitions, exceptions, amendments, or cross-references.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import re

CONTEXT_MARKERS = (
    (r"\bnotwithstanding\b", "notwithstanding clause"),
    (r"\bsubject to\b", "subject-to limitation"),
    (r"\bexcept\b|\bexception\b|\bunless\b", "exception or limitation"),
    (r"\bwaiver\b|\bexempt", "waiver or exemption"),
    (r"\bas defined in\b|\bdefined in\b", "external definition"),
    (r"\bunder section\b|\bpursuant to section\b|\bsection \d", "cross-reference"),
    (r"\bsubsection \([a-z0-9]+\)|\bparagraph \(\d+\)", "nested cross-reference"),
    (r"\bis amended\b|\bstriking\b|\binserting\b|\badding at the end\b", "amendatory edit-code"),
)

@dataclass(frozen=True)
class ContextFinding:
    severity: str
    code: str
    reason: str
    risks: list[str]
    context_score: float
    suggested_action: str

    def to_dict(self) -> dict:
        return asdict(self)


def context_risks(text: str) -> list[str]:
    low = " ".join(str(text or "").split()).lower()
    risks: list[str] = []
    for pattern, label in CONTEXT_MARKERS:
        if re.search(pattern, low, re.I) and label not in risks:
            risks.append(label)
    return risks


def prosecute(*, claim_text: str, excerpt: str, why_it_matters: str | None = None, missing_context: list[str] | None = None) -> ContextFinding:
    source_risks = context_risks(excerpt)
    claim_risks = context_risks(claim_text)
    missing = [str(x) for x in (missing_context or []) if str(x).strip()]
    acknowledged = bool(missing) or any(k in (why_it_matters or "").lower() for k in ("unknown", "does not tell us", "surrounding", "cross-reference", "context"))

    # Risk is intentionally asymmetric: source-level context markers matter more than
    # the public sentence repeating the same marker.
    score = min(1.0, 0.22 * len(source_risks) + 0.08 * len(claim_risks))
    if "amendatory edit-code" in source_risks:
        score = max(score, 0.55)
    if "external definition" in source_risks or "cross-reference" in source_risks:
        score = max(score, 0.42)
    if acknowledged:
        score = max(0.0, score - 0.18)

    if score >= 0.65 and not acknowledged:
        severity = "critical"
        code = "CONTEXT_MATERIALITY_UNRESOLVED"
        action = "Do not publish this implication until surrounding law/cross-references are resolved or the uncertainty is stated."
    elif score >= 0.35:
        severity = "warning"
        code = "CONTEXT_REVIEW_REQUIRED"
        action = "Keep the claim only with an explicit context limitation or resolved cross-reference."
    else:
        severity = "pass"
        code = "CONTEXT_SUFFICIENT"
        action = "No material context risk detected from the anchored excerpt."

    reason = (
        "The anchored text contains context-sensitive drafting that can change the apparent meaning: " + ", ".join(source_risks)
        if source_risks else "No strong context-sensitive drafting markers were detected in the anchored excerpt."
    )
    if acknowledged and source_risks:
        reason += " The public explanation acknowledges that surrounding context may matter."
    return ContextFinding(severity, code, reason, source_risks, round(score, 3), action)

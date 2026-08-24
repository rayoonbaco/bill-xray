"""Shared fiscal-materiality ontology for Bill X-Ray.

Pass 29.4 tightens the ontology from anchor-level to amount-level materiality.
A section may contain both operative tax/funding language and large contextual
figures (for example, national spending projections). Those contextual figures
must not inherit the section's fiscal label and outrank actual statutory money
mechanics.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FiscalMateriality:
    amount: float
    bucket: str
    directness: float
    score: float
    actionable: bool
    # Pass 30.1 provenance: explain exactly how this amount was graded.
    source_context: str = ""
    provenance: str = "legacy_fallback"
    context_kind: str = "unknown"


_CONTEXTUAL_AMOUNT_RE = re.compile(
    r"\b(?:project(?:ed|ion|ions)?|forecast(?:ed|s)?|estimate(?:d|s)?|"
    r"expected\s+to|anticipated\s+to|historical(?:ly)?|in\s+\d{4}\s+to\s+\$?|"
    r"national\s+(?:health\s+)?spending|market\s+size|economic\s+output)\b",
    re.I,
)


def _parse_amount(item: dict) -> float:
    raw = str(item.get("amount_usd") or item.get("normalized") or "").replace(",", "").strip()
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _amount_search_tokens(item: dict) -> list[str]:
    tokens: list[str] = []
    raw = " ".join(str(item.get("raw") or "").split()).strip()
    if raw:
        tokens.append(raw)
    amount = _parse_amount(item)
    if amount > 0:
        if float(amount).is_integer():
            tokens.extend([f"${amount:,.0f}", f"$ {amount:,.0f}"])
    # Longest first avoids a short fallback matching inside a larger number.
    return sorted(dict.fromkeys(tokens), key=len, reverse=True)


def _local_amount_context(text: str, item: dict, radius: int = 220) -> str | None:
    if not text:
        return None
    lower = text.lower()
    for token in _amount_search_tokens(item):
        pos = lower.find(token.lower())
        if pos >= 0:
            # Grade the clause/sentence containing this amount. A broad anchor-level
            # window lets projection language from one sentence contaminate an
            # operative tax/appropriation in the next sentence.
            left_candidates = [text.rfind(mark, 0, pos) for mark in (".", ";", "\n")]
            left = max(left_candidates) + 1
            right_candidates = [x for x in (text.find(mark, pos + len(token)) for mark in (".", ";", "\n")) if x >= 0]
            right = min(right_candidates) + 1 if right_candidates else len(text)
            clause = text[left:right].strip()
            if clause:
                return clause
            return text[max(0, pos - radius): min(len(text), pos + len(token) + radius)]
    return None


def _is_contextual_amount(context: str | None) -> bool:
    if not context:
        return False
    return bool(_CONTEXTUAL_AMOUNT_RE.search(context))


def _bucket(categories: set[str]) -> str:
    if "rescission" in categories:
        return "funding_reduction"
    if categories & {"appropriation", "funding"}:
        return "spending_authority"
    if categories & {"grant", "subsidy", "loan", "transfer"}:
        return "targeted_support"
    if categories & {"tax", "credit", "revenue", "fee"}:
        return "revenue_tax"
    return "unclassified"


def _directness_for_text(finding: dict, categories: set[str], text: str) -> float:
    status = str(finding.get("status") or "")
    if status == "needs_fiscal_context" and categories <= {"unclassified_money_amount"}:
        return 0.0

    text = " ".join(str(text or "").split()).lower()
    if not text:
        return 0.0

    if "appropriation" in categories and re.search(r"\b(?:appropriat(?:e|ed|es|ing|ion|ions)|authorized to be appropriated|hereby appropriated)\b", text):
        return 1.0
    if "rescission" in categories and re.search(r"\b(?:rescission|rescind(?:ed|s|ing)?)\b", text):
        return 1.0

    if categories & {"grant", "subsidy", "loan", "transfer"}:
        if re.search(r"\b(?:provide|award|make|issue|pay|transfer|disburse|allocate|available|establish)\w*\b", text):
            return 0.95
        return 0.72

    if categories & {"tax", "credit", "revenue", "fee"}:
        if re.search(r"\b(?:impose|increase|raise|collect|reduce|repeal|eliminate|decrease|allow|deny|credit|tax|fee|assessment)\w*\b", text):
            return 0.90
        return 0.62

    if "funding" in categories:
        if re.search(r"\b(?:provide|authorize|appropriate|allocate|make available|transfer|pay)\w*\b", text):
            return 0.82
        return 0.45

    return 0.0


def _amount_categories(item: dict, finding_categories: set[str]) -> set[str]:
    local = {str(x) for x in item.get("local_categories", []) if x}
    return local or finding_categories


def _context_for_amount(finding: dict, item: dict, text: str) -> tuple[str | None, str, str]:
    explicit = " ".join(str(item.get("context_excerpt") or "").split()).strip()
    if explicit:
        return explicit, "amount_provenance", str(item.get("context_kind") or "unknown")
    local = _local_amount_context(text, item)
    if local is not None:
        return local, "located_in_excerpt", "unknown"
    # Critical Pass 30.1 rule: if an amount from the full section cannot be found
    # in the stored excerpt, DO NOT grade it using unrelated section language.
    return None, "amount_context_missing", "unknown"


def assess_all(finding: dict) -> list[FiscalMateriality]:
    finding_categories = {str(x) for x in finding.get("categories", []) if x}
    text = " ".join(str(finding.get("operative_excerpt") or finding.get("review_reason") or "").split())
    results: list[FiscalMateriality] = []
    for item in finding.get("amounts", []):
        if not isinstance(item, dict):
            continue
        amount = _parse_amount(item)
        if amount <= 0:
            continue
        context, provenance, context_kind = _context_for_amount(finding, item, text)
        categories = _amount_categories(item, finding_categories)
        bucket = _bucket(categories)
        if context_kind == "context_projection" or _is_contextual_amount(context):
            results.append(FiscalMateriality(amount, bucket, 0.0, 0.0, False, context or "", provenance, "context_projection"))
            continue
        if context is None:
            results.append(FiscalMateriality(amount, bucket, 0.0, 0.0, False, "", provenance, context_kind))
            continue
        directness = _directness_for_text(finding, categories, context)
        actionable = bool(bucket != "unclassified" and directness >= 0.70)
        score = 0.0
        if actionable:
            magnitude = max(0.0, min(1.0, (math.log10(max(amount, 1.0)) - 5.0) / 7.0))
            score = round(magnitude * directness, 6)
        results.append(FiscalMateriality(amount, bucket, directness, score, actionable, context, provenance, context_kind))
    return results


def assess(finding: dict) -> FiscalMateriality:
    results = assess_all(finding)
    if not results:
        return FiscalMateriality(0.0, _bucket({str(x) for x in finding.get("categories", []) if x}), 0.0, 0.0, False)
    actionable = [x for x in results if x.actionable]
    pool = actionable or results
    return max(pool, key=lambda x: (x.score, x.amount))


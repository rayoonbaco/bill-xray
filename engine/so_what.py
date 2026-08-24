"""Pass 24/25 public explanations built from source-bound structured meaning packets."""
from __future__ import annotations

import re
from engine import meaning, comprehension, pass26_intelligence, fiscal_materiality, semantic_roles

_SENTENCE = re.compile(r"(?<=[.;!?])\s+(?=[A-Z(\[])" )


def compact(text: object) -> str:
    return " ".join(str(text or "").split())


def _clean_legal_markers(text: str) -> str:
    text = re.sub(r"<\/?NOTE[^>]*>", "", text, flags=re.I)
    text = re.sub(r"`+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _plain_modal(text: str) -> str:
    text = re.sub(r"\bshall not\b", "must not", text, flags=re.I)
    text = re.sub(r"\bshall\b", "must", text, flags=re.I)
    text = re.sub(r"\bmay not\b", "cannot", text, flags=re.I)
    text = re.sub(r"\bis authorized to\b", "may", text, flags=re.I)
    text = re.sub(r"\bare authorized to\b", "may", text, flags=re.I)
    return text


def _pick_clause(text: str, needles: list[str]) -> str:
    clean = _clean_legal_markers(compact(text))
    parts = [p.strip() for p in _SENTENCE.split(clean) if p.strip()] or ([clean] if clean else [])
    lowered_needles = [n.lower() for n in needles if n]
    for part in parts:
        low = part.lower()
        if any(n in low for n in lowered_needles):
            return part
    return parts[0] if parts else ""


def _clip(text: str, limit: int = 330) -> str:
    text = compact(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("; ", ". ", ", "):
        pos = cut.rfind(sep)
        if pos >= int(limit * 0.55):
            return cut[:pos].rstrip(" ,;:") + "."

    # Pass 32.1: never publish a bounded sentence that ends in the middle of a
    # numeric token. A display clip such as ``$25,000,000`` -> ``$2…`` creates a
    # new apparent money claim that did not exist in the approved source-bound
    # wording and correctly trips the strict citation auditor. If the hard limit
    # lands inside a number, retreat to the start of that token and mark the prose
    # as truncated there. The auditor remains unchanged and continues to reject
    # every complete novel number.
    trailing_number = re.search(r"(?<![A-Za-z0-9])\$?\d[\d,]*(?:\.\d*)?$", cut)
    if trailing_number:
        safe = cut[:trailing_number.start()].rstrip(" ,;:")
        if safe:
            return safe + "…"
    return cut.rstrip(" ,;:") + "…"


def money_packet(finding: dict):
    return meaning.from_money(finding)


def power_packet(finding: dict):
    return meaning.from_power(finding)


def money_explanation(finding: dict) -> tuple[str | None, str | None]:
    packet = meaning.from_money(finding)
    if packet and packet.plain_statement:
        challenge = comprehension.evaluate_packet(packet)
        if challenge.publish:
            roles = semantic_roles.resolve_money(finding, packet)
            assessment = fiscal_materiality.assess(finding)
            amount = f"${assessment.amount:,.0f}" if assessment.actionable and assessment.amount > 0 else None
            direction = str(finding.get("fiscal_direction") or "")
            if amount:
                if direction == "funding_reduction":
                    verb = "reduces or rescinds"
                elif direction == "government_receipt":
                    verb = "sets a tax, fee, or federal receipt rule involving"
                elif direction == "receipt_reduction":
                    verb = "reduces a tax, fee, or federal receipt by"
                else:
                    verb = "provides or sets"
                if roles.purpose:
                    text = f"{roles.actor or 'Congress'} {verb} {amount} for {roles.purpose}."
                else:
                    text = f"{roles.actor or 'Congress'} {verb} {amount}; the final use is not stated clearly enough here to name safely."
            else:
                text = packet.plain_statement
            details: list[str] = []
            if roles.recipient:
                details.append(f"Recipient or payer named here: {roles.recipient}. This identifies who receives it or who pays at this stage of the program.")
            if roles.period:
                details.append(f"When: {roles.period}.")
            if roles.unknowns:
                details.append("Still unknown: " + " ".join(roles.unknowns[:2]))
            why = " ".join(details) or (packet.why_it_matters or "")
            return _clip(text, 360), _clip(why, 430) if why else None
    amounts = [compact(x.get("raw") or x.get("normalized")) for x in finding.get("amounts", []) if isinstance(x, dict) and compact(x.get("raw") or x.get("normalized"))]
    cats = [str(x).replace("_", " ") for x in finding.get("categories", []) if x]
    if amounts or cats:
        text = f"In plain English: this provision names {', '.join(amounts[:2]) or 'a money rule'} in a federal {', '.join(cats[:2]) or 'funding'} provision."
        why = "Why it matters: the source excerpt is needed to identify safely who pays, who receives the money, and the stated purpose."
        return _clip(text, 330), _clip(why, 300)
    return None, None


def power_explanation(finding: dict) -> tuple[str | None, str | None]:
    packet = meaning.from_power(finding)
    if packet and packet.plain_statement:
        challenge = comprehension.evaluate_packet(packet)
        if challenge.publish:
            roles = semantic_roles.resolve_power(finding, packet)
            text = packet.plain_statement
            if roles.actor and roles.action:
                text = f"{roles.actor} {roles.action}"
            details: list[str] = []
            if roles.target:
                details.append(f"Who or what is affected: {roles.target}.")
            if packet.authority_type:
                details.append(f"Type of power or duty: {packet.authority_type}.")
            if packet.why_it_matters:
                details.append(packet.why_it_matters.replace("Why it matters:", "Practical consequence:", 1))
            if roles.unknowns:
                details.append("Still unknown: " + " ".join(roles.unknowns[:1]))
            return _clip(text, 350), _clip(" ".join(details), 450) if details else None
    actors = [compact(x) for x in finding.get("actors", []) if compact(x)]
    kinds = [str(x).replace("_", " ") for x in finding.get("authority_types", []) if x]
    if actors or kinds:
        subject = ", ".join(actors[:2]) or "The government actor named here"
        text = f"In plain English: {subject} has a federal authority provision involving {', '.join(kinds[:2]) or 'government power'}."
        why = "Why it matters: the source clause is needed to say safely what concrete action becomes required, allowed, or prohibited."
        return _clip(text, 330), _clip(why, 300)
    return None, None


def scrutiny_explanation(candidate: dict) -> tuple[str | None, str | None, str | None]:
    labels = [str(x) for x in candidate.get("labels", []) if x]
    excerpt = compact(candidate.get("operative_excerpt"))
    reasons = [compact(x) for x in candidate.get("why_flagged", []) if compact(x)]
    factors = candidate.get("factors") or {}
    independent = max(
        float(factors.get("beneficiary_concentration", 0.0)),
        float(factors.get("fiscal_significance", 0.0)),
        float(factors.get("scope_surprise", 0.0)),
        float(factors.get("cross_reference_opacity", 0.0)),
        float(factors.get("narrow_carve_out", 0.0)),
    )
    if not labels or independent < 0.35:
        return None, None, None
    nonlex = [r for r in reasons if "lexically distant" not in r.lower()]
    if not nonlex:
        return None, None, None

    label = labels[0]
    clause = _plain_modal(_pick_clause(excerpt, ["except", "waiver", "exempt", "$", "only", "notwithstanding", "section"]))
    if clause:
        text = f"{label}: {_clip(clause, 260)}"
    else:
        text = f"{label}: {_clip(nonlex[0], 260)}"
    why = "What stands out: " + _clip(" ".join(nonlex[:2]), 260)
    return _clip(text, 330), label, _clip(why, 300)


def main_effect_from_findings(money: dict | None, power: dict | None) -> tuple[str | None, str | None, str | None]:
    """Return the canonical public consequence used by synthesis *and* audit.

    Pass 31.2.1 removes a split provenance path: synthesis previously selected a
    MeaningPacket.plain_statement here while the citation audit regenerated the
    newer semantic-role explanation. Both were source-bound, but they could differ
    word-for-word and therefore correctly trip the reproducibility gate.

    Selection still uses the structured packet completeness score. Publication text
    is now generated only through money_explanation / power_explanation, which are
    the same semantic-role-aware helpers the audit independently regenerates.
    """
    candidates: list[tuple[object, dict, str]] = []
    if money:
        packet = meaning.from_money(money)
        if packet:
            candidates.append((packet, money, "money"))
    if power:
        packet = meaning.from_power(power)
        if packet:
            candidates.append((packet, power, "power"))

    candidates.sort(key=lambda row: row[0].completeness_score, reverse=True)
    for packet, finding, kind in candidates:
        if packet.completeness_score < 0.55:
            continue
        if not comprehension.evaluate_packet(packet).publish:
            continue
        if kind == "money":
            text, why = money_explanation(finding)
        else:
            text, why = power_explanation(finding)
        if text:
            return text, why, kind
    return None, None, None

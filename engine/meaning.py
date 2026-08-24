"""Pass 25: deterministic, source-bound meaning packets.

The meaning layer is intentionally conservative. It does not guess motive, policy
success, downstream economics, or unstated beneficiaries. It turns already-extracted
money/power findings into a structured packet that answers the human questions we can
support from the same statutory anchor: who acts, what action changes, who/what is the
target, what money is named, what purpose is stated, and what important context remains
unknown.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import re

from engine import fiscal_materiality

_MODAL = re.compile(
    r"\b(shall not|must not|may not|shall|must|may|is authorized to|are authorized to|is required to|are required to)\b",
    re.I,
)
_ACTOR = re.compile(
    r"\b(the President|the Vice President|the Attorney General|the Secretary(?: of [A-Z][A-Za-z& ,\-]+)?|"
    r"the Administrator(?: of [A-Z][A-Za-z& ,\-]+)?|the Director(?: of [A-Z][A-Za-z& ,\-]+)?|"
    r"the Commissioner(?: of [A-Z][A-Za-z& ,\-]+)?|the Comptroller General|the Inspector General|"
    r"the Commission|the Board|the Department(?: of [A-Z][A-Za-z& ,\-]+)?|the Agency|Congress|"
    r"a State|the State|States)\b",
    re.I,
)
_AMOUNT = re.compile(r"\$\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:trillion|billion|million|thousand))?", re.I)
_SENTENCE = re.compile(r"(?<=[.;!?])\s+(?=[A-Z(\[])" )


@dataclass(frozen=True)
class MeaningPacket:
    source_kind: str
    actor: str | None
    action: str | None
    target: str | None
    amounts: list[str]
    recipient: str | None
    purpose: str | None
    authority_type: str | None
    exception: str | None
    plain_statement: str | None
    why_it_matters: str | None
    missing_context: list[str]
    completeness_score: float

    def to_dict(self) -> dict:
        return asdict(self)


def compact(value: object) -> str:
    return " ".join(str(value or "").split())


def _clean(text: str) -> str:
    text = re.sub(r"<\/?NOTE[^>]*>", "", text, flags=re.I)
    text = re.sub(r"`+", "", text)
    return compact(text)


def _plain_modal(text: str) -> str:
    replacements = (
        (r"\bshall not\b", "must not"),
        (r"\bshall\b", "must"),
        (r"\bmay not\b", "cannot"),
        (r"\bis required to\b", "must"),
        (r"\bare required to\b", "must"),
        (r"\bis authorized to\b", "may"),
        (r"\bare authorized to\b", "may"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return compact(text)


def _clip(text: str | None, limit: int = 300) -> str | None:
    if not text:
        return None
    text = compact(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("; ", ". ", ", "):
        pos = cut.rfind(sep)
        if pos >= int(limit * .55):
            return cut[:pos].rstrip(" ,;:") + "."

    # Pass 32.1.1: this is the earliest semantic-role bounding layer. Never
    # manufacture a new apparent number by placing an ellipsis inside a numeric
    # token (for example, ``$25,000,000`` -> ``$2…``). Retreat to the start of
    # an incomplete trailing numeric token; complete numbers remain untouched.
    trailing_number = re.search(r"(?<![A-Za-z0-9])\$?\d[\d,]*(?:\.\d*)?$", cut)
    if trailing_number:
        safe = cut[:trailing_number.start()].rstrip(" ,;:")
        if safe:
            return safe + "…"
    return cut.rstrip(" ,;:") + "…"


def _sentence_case(text: str | None) -> str | None:
    text = compact(text)
    if not text:
        return None
    return text[0].upper() + text[1:]


def _append_sentence(base: str | None, extra: str | None) -> str | None:
    base = compact(base)
    extra = compact(extra)
    if not base:
        return extra or None
    if not extra:
        return base
    if base[-1] not in ".!?":
        base += "."
    return base + " " + extra


def _sentences(text: str) -> list[str]:
    clean = _clean(text)
    pieces = [p.strip() for p in _SENTENCE.split(clean) if p.strip()]
    return pieces or ([clean] if clean else [])


def _best_clause(text: str, needles: list[str]) -> str:
    parts = _sentences(text)
    lowered = [compact(n).lower() for n in needles if compact(n)]
    for part in parts:
        low = part.lower()
        if any(n in low for n in lowered):
            return part
    return parts[0] if parts else ""


def _actor_from(clause: str, explicit: list[str] | None = None) -> str | None:
    if explicit:
        for item in explicit:
            item = compact(item)
            if item and item.lower() in clause.lower():
                return item
        # Never bind an actor extracted elsewhere in a long section to a clause that
        # does not actually name that actor. That creates a false actor/action pair.
    match = _ACTOR.search(clause)
    return compact(match.group(0)) if match else None


def _action_from(clause: str, actor: str | None) -> str | None:
    plain = _plain_modal(clause)
    start = 0
    if actor:
        pos = plain.lower().find(actor.lower())
        if pos >= 0:
            start = pos + len(actor)
    tail = plain[start:].strip(" ,:;-")
    modal = re.search(r"\b(must not|cannot|must|may)\b", tail, re.I)
    if modal:
        action = tail[modal.start():]
    else:
        action = tail
    action = re.split(r"(?=\bprovided that\b|\bexcept that\b)", action, maxsplit=1, flags=re.I)[0]
    return _clip(action.strip(" ,;:"), 220)


def _target_from(action: str | None) -> str | None:
    if not action:
        return None
    patterns = (
        r"\bnotify\s+(?:the\s+)?(.+?)(?=\s+and\s+(?:may|must|shall|cannot)\b|[,;.]|$)",
        r"\bprovide\s+(?:the\s+)?(.+?)(?=\s+and\s+(?:may|must|shall|cannot)\b|[,;.]|$)",
        r"\bpay\s+(?:the\s+)?(.+?)(?=\s+and\s+(?:may|must|shall|cannot)\b|[,;.]|$)",
        r"\bgrants?\s+to\s+([^,;.]+)",
        r"\bto\s+(eligible\s+[^,;.]+)",
        r"\b(?:establish|establishing|create|creating|set|setting)\s+(?:the\s+)?([^,;.]+)",
        r"\bfor\s+([^,;.]+)",
    )
    for pattern in patterns:
        m = re.search(pattern, action, re.I)
        if m:
            value = compact(m.group(1)).strip(" .;,")
            if 2 <= len(value) <= 120:
                return value
    return None


def _money_recipient_purpose(clause: str) -> tuple[str | None, str | None]:
    plain = _plain_modal(clause)
    recipient = purpose = None
    # Typical appropriations form: "$X to the Secretary for grants to eligible States"
    m = re.search(r"\$\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:trillion|billion|million|thousand))?\s+to\s+(.+?)(?:\s+for\s+|[.;]|$)", plain, re.I)
    if m:
        recipient = compact(m.group(1)).strip(" ,;.")
    p = re.search(r"\bfor\s+(.+?)(?:[.;]|$)", plain, re.I)
    if p:
        purpose = compact(p.group(1)).strip(" ,;.")
    g = re.search(r"\bgrants?\s+to\s+(.+?)(?:[.;]|$)", plain, re.I)
    if g:
        # For a grant, the grantee is the practical recipient even when funds are first
        # appropriated "to the Secretary" for administration.
        recipient = compact(g.group(1)).strip(" ,;.")
    return _clip(recipient, 130), _clip(purpose, 180)


def _exception_from(clause: str) -> str | None:
    m = re.search(r"\b(except(?:ion)?[^.;]*|unless[^.;]*|waiver[^.;]*|exempt(?:ion|ed)?[^.;]*)", clause, re.I)
    return _clip(compact(m.group(1)), 180) if m else None


def _score(*, actor: str | None, action: str | None, target: str | None, amounts: list[str], recipient: str | None, purpose: str | None) -> float:
    score = 0.0
    score += .25 if actor else 0
    score += .35 if action else 0
    score += .10 if target else 0
    score += .10 if amounts else 0
    score += .10 if recipient else 0
    score += .10 if purpose else 0
    return round(min(1.0, score), 2)


def from_power(finding: dict) -> MeaningPacket | None:
    excerpt = compact(finding.get("operative_excerpt"))
    if not excerpt:
        return None
    actors = [compact(x) for x in finding.get("actors", []) if compact(x)]
    kinds = [str(x).replace("_", " ") for x in finding.get("authority_types", []) if x]
    clause = _best_clause(excerpt, actors[:2] + ["shall", "may", "authorized", "prohibit", "waiver", "enforce", "rule"])
    actor = _actor_from(clause, actors)
    action = _action_from(clause, actor)
    target = _target_from(action)
    exception = _exception_from(clause)
    authority_type = kinds[0] if kinds else None

    plain_statement = None
    if actor and action:
        plain_statement = _sentence_case(f"{actor} {action}")
    elif action:
        plain_statement = _sentence_case(action)

    why = None
    if actor and action:
        low = action.lower()
        kindset = set(kinds)
        if "enforcement" in kindset:
            why = f"Why it matters: this changes how {actor} can investigate, enforce, penalize, or otherwise carry out federal law."
            if low.startswith("must "):
                why = _append_sentence(why, "It also makes the stated action a legal duty rather than an option.")
        elif "rulemaking" in kindset:
            why = f"Why it matters: this lets {actor} shape the rules that determine how this part of the law works in practice."
        elif "waiver or exemption" in kindset:
            why = f"Why it matters: this can change who must follow the rule and who {actor} can excuse from it."
        elif "prohibition or limit" in kindset or "must not" in low or "cannot" in low:
            why = f"Why it matters: this places a concrete legal limit on what {actor} can do."
        elif low.startswith("must "):
            why = f"Why it matters: this makes that action a legal duty for {actor}, not an optional step."
        elif low.startswith("may "):
            why = f"Why it matters: this gives {actor} legal discretion or authority to take that action."
        else:
            why = f"Why it matters: this changes the legal job or authority of {actor}."
        if target:
            why = _append_sentence(why, f"The immediate target named in the text is {target}.")

    missing: list[str] = []
    if not actor:
        missing.append("The responsible government actor is not explicit in this clause.")
    if not target:
        missing.append("The immediate affected person or entity is not explicit enough to name safely.")
    if finding.get("status") == "needs_legal_context":
        missing.append("Cross-references or surrounding law may change the full scope of this authority.")

    return MeaningPacket(
        source_kind="power", actor=actor, action=action, target=target, amounts=[], recipient=None,
        purpose=None, authority_type=authority_type, exception=exception,
        plain_statement=_clip(_plain_modal(plain_statement or ""), 300),
        why_it_matters=_clip(why, 300), missing_context=missing,
        completeness_score=_score(actor=actor, action=action, target=target, amounts=[], recipient=None, purpose=None),
    )


def from_money(finding: dict) -> MeaningPacket | None:
    excerpt = compact(finding.get("operative_excerpt"))
    assessment = fiscal_materiality.assess(finding)
    amount_items = [x for x in finding.get("amounts", []) if isinstance(x, dict)]
    selected_item = None
    if assessment.actionable and assessment.amount > 0:
        for item in amount_items:
            raw_value = str(item.get("amount_usd") or item.get("normalized") or "").replace(",", "").strip()
            try:
                if float(raw_value) == float(assessment.amount):
                    selected_item = item
                    break
            except ValueError:
                continue
    amounts = []
    if selected_item:
        rendered = compact(selected_item.get("raw") or selected_item.get("normalized") or selected_item.get("amount_usd"))
        if rendered:
            amounts = [rendered]
    cats = [str(x).replace("_", " ") for x in finding.get("categories", []) if x]
    if not excerpt and not amounts:
        return None
    # Pass 31: when an actionable amount has canonical clause provenance, explain that
    # clause instead of searching a truncated section excerpt that may contain unrelated numbers.
    canonical_clause = compact((selected_item or {}).get("context_excerpt")) if selected_item else ""
    clause = canonical_clause or _best_clause(excerpt, amounts[:1] + cats[:2] + ["appropriated", "grant", "tax", "credit", "fee", "revenue"])
    actor = _actor_from(clause)
    action = _action_from(clause, actor)
    recipient, purpose = _money_recipient_purpose(clause)
    target = recipient or _target_from(action)
    exception = _exception_from(clause)

    amount_phrase = ", ".join(amounts[:2])
    lower = clause.lower()
    plain_statement = None
    if amount_phrase and re.search(r"\bappropriat(?:e|ed|ion)\b", lower):
        if recipient and purpose and re.search(r"\bgrants?\s+to\b", purpose, re.I):
            plain_statement = f"Congress provides {amount_phrase} as {purpose}."
        elif recipient and purpose:
            plain_statement = f"Congress provides {amount_phrase} to {recipient} for {purpose}."
        elif recipient:
            plain_statement = f"Congress provides {amount_phrase} to {recipient}."
        else:
            plain_statement = f"Congress provides {amount_phrase} in this provision."
    elif amount_phrase and action and actor:
        plain_statement = f"{actor} {action}"
    elif amount_phrase:
        plain_statement = _plain_modal(clause)
    elif action and actor:
        plain_statement = f"{actor} {action}"

    direction = str(finding.get("fiscal_direction") or "")
    why = None
    if direction == "funding_reduction":
        why = "Why it matters: this reduces or takes back public funding that had otherwise been available."
    elif direction == "government_receipt":
        why = "Why it matters: this increases or changes money flowing into the federal government from taxpayers, businesses, or other payers."
    elif direction == "receipt_reduction":
        why = "Why it matters: this reduces a tax, fee, or other government receipt for the people or entities that would otherwise pay it."
    elif amount_phrase and recipient:
        why = f"Why it matters: the text directs a concrete amount of public money toward {recipient}; that answers who receives it at this stage of the program."
    elif amount_phrase:
        why = "Why it matters: the text commits or changes a concrete amount of public money."
    else:
        why = "Why it matters: this changes a federal tax, revenue, or funding rule."
    if purpose:
        why = _append_sentence(why, f"The stated purpose is {purpose}.")

    missing: list[str] = []
    had_money_amount = bool(amount_items)
    if had_money_amount and not recipient:
        missing.append("This clause names money but does not clearly identify the final recipient.")
    if had_money_amount and not purpose:
        missing.append("This clause does not clearly state the final use of the money.")
    if finding.get("status") == "needs_fiscal_context":
        missing.append("The bill section needs additional fiscal context before treating this as a net budget effect.")

    return MeaningPacket(
        source_kind="money", actor=actor, action=action, target=target, amounts=amounts,
        recipient=recipient, purpose=purpose, authority_type=None, exception=exception,
        plain_statement=_clip(plain_statement, 320), why_it_matters=_clip(why, 320),
        missing_context=missing,
        completeness_score=_score(actor=actor, action=action, target=target, amounts=amounts, recipient=recipient, purpose=purpose),
    )


def best(money: dict | None, power: dict | None) -> MeaningPacket | None:
    packets = [p for p in (from_power(power or {}) if power else None, from_money(money or {}) if money else None) if p and p.plain_statement]
    if not packets:
        return None
    # Prefer the packet that answers more human questions. Money wins ties because an
    # explicit fiscal consequence is usually more concrete for the public surface.
    return sorted(packets, key=lambda p: (p.completeness_score, 1 if p.source_kind == "money" else 0), reverse=True)[0]

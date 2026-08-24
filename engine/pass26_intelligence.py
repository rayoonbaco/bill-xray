"""Pass 26: concrete money-flow, affected-party, and substantive lens helpers.

This module stays source-bound. It does not infer motive, fraud, net budget effects,
or downstream winners/losers that are not supported by the same statutory anchor.
It turns Pass 25 meaning packets into clearer public-facing decision language and
creates paired political interpretations that argue about the same concrete effect.
"""
from __future__ import annotations

from engine.meaning import MeaningPacket, compact


def _trim(text: str, limit: int = 360) -> str:
    text = compact(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip(" ,;:") + "…"


def money_public(packet: MeaningPacket) -> tuple[str | None, str | None]:
    if packet.source_kind != "money" or not packet.plain_statement:
        return None, None
    details: list[str] = []
    if packet.recipient:
        details.append(f"Direct recipient named in the text: {packet.recipient}. This answers who receives it at this stage of the program.")
    if packet.purpose:
        details.append(f"Stated purpose: {packet.purpose}.")
    if packet.missing_context:
        details.append("Still unknown from this provision alone: " + " ".join(packet.missing_context[:2]))
    why = " ".join(details) or (packet.why_it_matters or "")
    return _trim(packet.plain_statement), _trim(why, 420) if why else None


def power_public(packet: MeaningPacket) -> tuple[str | None, str | None]:
    if packet.source_kind != "power" or not packet.plain_statement:
        return None, None
    details: list[str] = []
    if packet.target:
        details.append(f"Directly affected: {packet.target}.")
    if packet.authority_type:
        details.append(f"Type of power or duty: {packet.authority_type}.")
    if packet.exception:
        details.append(f"Exception or carve-out named here: {packet.exception}.")
    if packet.why_it_matters:
        details.append(packet.why_it_matters.replace("Why it matters:", "Practical consequence:", 1))
    if packet.missing_context:
        details.append("Still unknown from this provision alone: " + " ".join(packet.missing_context[:1]))
    return _trim(packet.plain_statement), _trim(" ".join(details), 440) if details else None


def _effect(packet: MeaningPacket) -> str:
    return packet.plain_statement.rstrip(". ") if packet.plain_statement else "this provision"


def _money_pair(packet: MeaningPacket) -> tuple[str, str]:
    effect = _effect(packet)
    recipient = packet.recipient or packet.target or "the recipient named in the provision"
    purpose = packet.purpose or "the stated federal purpose"
    amount = ", ".join(packet.amounts[:2]) or "federal money"
    left = (
        f"A progressive reading would judge this concrete choice: {effect}. "
        f"Its strongest case is that directing {amount} toward {recipient} for {purpose} can expand public capacity or access; "
        f"its key test is whether the benefit is fairly distributed and reaches the people the program is meant to serve."
    )
    right = (
        f"A conservative reading would judge the same concrete choice: {effect}. "
        f"Its strongest concern is whether committing {amount} through the federal government to {recipient} for {purpose} is necessary, well targeted, and worth the taxpayer cost or market distortion."
    )
    return _trim(left, 520), _trim(right, 520)


def _power_pair(packet: MeaningPacket) -> tuple[str, str]:
    effect = _effect(packet)
    target = packet.target or "the people or entities covered by the provision"
    kind = (packet.authority_type or "government authority").lower()
    low = (packet.action or "").lower()
    if "prohibition" in kind or "limit" in kind or low.startswith("must not") or low.startswith("cannot"):
        left_focus = f"whether this limit protects {target} from overreach and makes government power more accountable"
        right_focus = f"whether this limit preserves constitutional boundaries without preventing effective enforcement or administration affecting {target}"
    elif "enforcement" in kind:
        left_focus = f"whether the enforcement power affecting {target} includes fair process, equal treatment, and meaningful accountability"
        right_focus = f"whether the enforcement power affecting {target} gives government enough capacity to carry out the law while staying within clear legal limits"
    elif "waiver" in kind or "exemption" in kind:
        left_focus = f"who receives relief from the rule, who remains subject to it, and whether {target} is treated fairly"
        right_focus = f"whether the flexibility for {target} reduces unnecessary federal rigidity without creating arbitrary favoritism"
    else:
        left_focus = f"how this change in government power affects {target}, public accountability, and equal treatment"
        right_focus = f"whether this change gives government the right amount of authority over {target} without unnecessary federal reach"
    left = f"A progressive reading would focus on this concrete change: {effect}. Its strongest question is {left_focus}."
    right = f"A conservative reading would focus on the same concrete change: {effect}. Its strongest question is {right_focus}."
    return _trim(left, 500), _trim(right, 500)


def substantive_lens_pair(packet: MeaningPacket | None) -> tuple[str | None, str | None]:
    if not packet or not packet.plain_statement:
        return None, None
    if packet.source_kind == "money":
        return _money_pair(packet)
    if packet.source_kind == "power":
        return _power_pair(packet)
    return None, None

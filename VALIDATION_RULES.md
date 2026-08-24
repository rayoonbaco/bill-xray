# Validation Rules

## Claim validity
Reject any consequential claim without a citation anchor.

## Political symmetry
Apply identical analysis rules to all bills regardless of sponsor, president, party, or subject.

## Barrel Scan
A high Barrel Scan score means "deserves inspection," not "is corrupt."

## Language
Prefer:
- "potential rider"
- "scope surprise"
- "narrow carve-out"
- "specific beneficiary"
- "cross-reference opacity"

Avoid unsupported labels such as:
- corruption
- fraud
- scam
- illegal
- hidden agenda

## Expert escalation
Mark low-confidence or legally ambiguous issues as expert-review candidates.

## Plain-English translation
A translation is a reading aid, not new evidence. It must remain bound to a verified citation anchor, preserve legal force and material qualifiers, and never introduce intent or downstream effects. If the full anchored unit cannot be translated safely, route it to expert review rather than display a partial or guessed summary.

## Power / authority extraction
Authority findings must remain textual until later expert review. Preserve the actor, modality, verified anchor, and legal mechanic. Do not infer constitutionality, overall size of government, political motive, likely use, or beneficiary from authority language alone. Cross-reference-dependent or actor-ambiguous findings must route to legal-context review.

## Pass 9 — Dynamic Topic Expert
- Topic routing must start from a verified Pass 4 anchor.
- Routing is section-level; whole-bill reputation cannot determine the section's expert.
- Multiple experts are allowed when evidence supports overlapping domains.
- Weak routing must become `needs_human_topic_assignment`, not a fabricated specialist match.
- Topic-review packets are internal review material (`UNKNOWN`) until later evidence/referee passes admit a substantive claim.
- Prior Money, Power, and Barrel Scan artifacts may be joined only by exact anchor ID.

## Pass 10 — Left Lens
- The Left Lens is advocacy, never statutory fact.
- Every Left Lens candidate must remain `lens: LEFT` and `claim_class: INTERPRETATION` unless later evidence forces `DISPUTED`.
- Every candidate must retain a verified Pass 4 anchor and source/text fingerprints.
- Prior evidence layers may be joined only by exact anchor ID.
- Missing fiscal, legal, distributional, beneficiary, implementation, or topic evidence must be surfaced as missing context, not guessed.
- A Barrel Scan flag cannot be converted into favoritism, impropriety, corruption, or motive.
- The progressive advocate must state the strongest good-faith case and identify a serious counterweight that could weaken it.
- Party sponsorship, president, public reputation, or bill nickname cannot determine the argument.


## Left/Right source symmetry

- Advocacy lanes may disagree about values, risks, and policy interpretation; they may not receive different statutory facts.
- Left and Right candidates for the same anchor must retain the same `anchor_id`, source fingerprint, text fingerprint, and source-bound evidence snapshot.
- Both advocacy lanes remain `INTERPRETATION` and must surface missing context rather than upgrading uncertainty into fact.

## Pass 12 — Investigative Skeptic
- The skeptic must review Left and Right from an identical source-bound evidence record.
- Any asymmetry in anchor identity, source/text fingerprints, evidence layers, or evidence snapshots blocks downstream comparison.
- Acknowledged context gaps must remain visible; they cannot be polished away.
- Barrel Scan candidates trigger an explicit overreach check and remain scrutiny flags only.
- The skeptic challenges causal leaps, rhetorical inflation, and cherry-picking but does not itself publish accusations or choose a political side.

## Pass 13 — Neutral Referee
- The referee is an evidence gatekeeper, not a centrist averaging function.
- LEFT/RIGHT agreement cannot upgrade INTERPRETATION into TEXT or DIRECT_EFFECT.
- LEFT/RIGHT disagreement cannot downgrade clear anchored statutory language.
- TEXT requires verified anchored statutory support.
- DIRECT_EFFECT requires an explicit legal/fiscal mechanic with no unsupported downstream causal step.
- LIKELY_EFFECT requires appropriate external evidence and exposed assumptions; statutory text alone is insufficient.
- INTERPRETATION remains visibly labeled as LEFT or RIGHT advocacy.
- Material unresolved conflict may become DISPUTED; insufficient support must remain UNKNOWN.
- Critical source/asymmetry challenges block publication from the affected anchor.
- High-severity context gaps restrict Pass 14 to bounded text/direct-effect material that does not depend on the missing context.
- Barrel Scan output may be admitted only as a reason for scrutiny, never as proof of corruption, waste, favoritism, illegality, or motive.
- Pass 14 may compress referee-admitted material but may not upgrade a claim class or rescue a blocked claim through prose.

## Pass 14 — Five-panel synthesis

- Public synthesis must contain exactly the five canonical panels in canonical order.
- No panel may exceed three claims.
- Every public claim must retain a Pass 4 `anchor_id`.
- Blocked referee anchors may not enter synthesis.
- `LIKELY_EFFECT` remains excluded until suitable external evidence has been admitted.
- LEFT and RIGHT public claims remain `INTERPRETATION` or `DISPUTED`.
- A verified LEFT | RIGHT | TEXT panel must contain exactly LEFT, RIGHT, TEXT in that order.
- Panel 1 requires at least one verified plain-English TEXT finding.
- Panels 2–4 may be empty when the referee admits no appropriate finding; the UI must not invent filler.
- Synthesis may rank and compress evidence but may not create new legal, fiscal, causal, beneficiary, motive, or corruption claims.

## Pass 15 — Evidence drawer / source navigation

- Every visible claim in a verified analysis must expose its Pass 4 `anchor_id` through a one-click Evidence control.
- Evidence display must resolve the anchor against the current canonical ingested source at click time; stale fingerprints fail closed.
- The drawer must show exact anchored source text, not an LLM reconstruction of the text.
- Source navigation may link to the retained official source URL but must not imply that a generic source URL lands on the exact anchored line.
- Evidence navigation is read-only: it may not alter claim text, class, confidence, lens, referee status, or Barrel Scan meaning.
- Closing evidence must return the reader to the same five-panel summary rather than sending them through a separate navigation flow.

## Pass 17 real-bill proving-ground rules

- Real-bill runners MUST identify the exact official public law before analysis.
- Source acquisition MUST finish before the local ingestion boundary begins.
- Every long-running stage MUST announce itself before execution and flush output immediately.
- Every completed stage MUST record elapsed time in a durable progress checkpoint.
- A failed run MUST preserve the last completed stage and must not publish claims from an incomplete chain.
- ACA and OBBBA MUST use the same 14-stage evidence sequence.
- Curated proving-ground advocacy prose remains `INTERPRETATION` and MUST be paired on the same citation anchor.
- The familiar bill nickname MUST NOT replace the official public-law identity in provenance.

## Pass 18 — Political-Bias + Selection-Quality Red Team

- A cited claim can still fail release if selection quality is poor.
- LEFT, RIGHT, and TEXT must refer to the same citation anchor in the public comparison panel.
- LEFT and RIGHT stay classified as INTERPRETATION or DISPUTED and receive symmetric evidence identity.
- Political framing may not leak outside labeled advocacy lanes.
- Follow the Money must prefer material explicit statutory amounts over token figures when larger quantified candidates are available.
- Barrel Scan may not publish lexical topical distance as a persuasive rationale without an independent scrutiny signal.
- Source-like legalese that fails the Kitchen Table Test is held off the front page even when its citation is valid.


## Pass 19 release gate
- Every public claim must re-resolve through its stable Pass 4 anchor against the current canonical source.
- Public citation metadata must match the canonical anchor.
- Published wording must be reproducible from the upstream source-bound artifact used by synthesis.
- TEXT and DIRECT_EFFECT claims may not introduce numeric tokens absent from their anchored statutory text.
- A failed hallucination/citation audit blocks release; the audit never rewrites evidence.


## Panel 5 language-gate separation (Pass 19.2)

- WHAT IT REALLY DOES may reject a safe translation for being too source-like.
- That rejection alone must not delete a same-anchor TEXT referee proposition from LEFT | RIGHT | TEXT.
- Panel 5 TEXT must still originate from a successful source-grounded translator packet and an admissible referee TEXT lane.
- LEFT, RIGHT, and TEXT must remain on one citation anchor; otherwise Panel 5 stays unpublished.


## TEXT referee construction (Pass 19.3)
- Panel 5 TEXT must be constructed from the same verified Pass 4 anchor as LEFT and RIGHT.
- Panel 5 TEXT does not depend on whole-section translator success.
- The constructor is extractive: it may normalize source formatting but may not add political, causal, or predicted-effect language.
- The Neutral Referee must admit TEXT on the anchor before the statement can publish.
- Pass 19 citation audit must independently reconstruct the same TEXT statement from the current canonical source.

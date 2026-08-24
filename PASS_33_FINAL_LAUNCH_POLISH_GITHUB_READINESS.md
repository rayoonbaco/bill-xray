# PASS 33 — Final Launch Polish / GitHub Readiness

## Scope
Launch hardening only. No new analytical features and no weakening of release gates.

## Findings and decisions
- The Grandma smoke test had zero red flags after Pass 32.2.
- The remaining pytest packaging-policy warning was stale: it assumed an upgrade patch must never contain showcase analyses. Pass 32 intentionally deploys four verified prebuilt exhibits, so the regression now rejects placeholder/unverified showcase analyses rather than rejecting verified release artifacts merely for existing.
- IRA's 0.950 `pass_with_warnings` red-team result is a readability warning (`PUBLIC_LEGALESE`) with zero critical findings, not evidence of Left/Right asymmetry. Claim wording is not silently rewritten at launch because doing so would require fresh provenance/audit approval.
- Public deployment is read-only. Search/import/build mutation endpoints are disabled when `BILL_XRAY_PUBLIC_MUSEUM=1`; local development behavior remains unchanged.
- Render and GitHub packaging are explicit and reproducible.

## Human-in-the-loop note
The launch smoke-test layer was added after the human operator asked a different acceptance question: not merely whether the pipeline ran, but what else could make the public product confusing or untrustworthy. That reframing exposed stale legacy provenance and an incomplete test environment, both of which were corrected before launch.

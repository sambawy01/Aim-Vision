# ADR-0015: Phase 1 Ships Full Minor-Athlete Support

**Status:** Accepted · **Date:** 2026-05-24 · **Owner:** Product / Compliance

## Context

Youth shooting is a meaningful share of competitive shotgun sports;
the Egypt National Team (ADR-0016 pilot venue) fields a junior squad,
and many federations the platform is designed for run youth-development
programmes. Shipping a coaching platform for shooters and *excluding
minors* would carve out the segment that arguably most needs the
diagnostic transparency the platform provides.

The compliance debt to ship minors *correctly* is real and was the
"defer it" argument:

- COPPA (US, < 13) requires verifiable parental consent — ADR-0011
  addresses this via Stripe card verification.
- GDPR / GDPR-K (EU, < 16 default) requires verifiable consent of
  the holder of parental responsibility — same Stripe flow plus
  per-purpose consent capture (already built in
  `aimvision-mobile/src/screens/onboarding/ConsentMatrixScreen.tsx`).
- Egypt PDPL (`docs/compliance/egypt-pdpl-action-plan.md`) requires
  guardian consent for minors and explicit purpose limitation.
- COPPA requires data-minimisation, no behavioural advertising, no
  data sale, and an honoured deletion path — the right-to-erasure
  architecture (PR #84 backend, PR #85 UI) covers the deletion path.

All of the *infrastructure* is built. The remaining work to "make
minors safe to launch with" is: wire the Stripe consent backend
(ADR-0011), wire the consent-matrix submit endpoint server-side,
have legal counsel sign off on the parental-consent + privacy-notice
copy in EN + AR, and exercise the deletion path against a real
minor's data end-to-end.

Deferring minors means turning the platform's headline value
proposition off for the design partner's primary user-base.

## Decision

**Minor-athlete support ships fully in Phase 1.** Specifically:

- Age gate (already built —
  `aimvision-mobile/src/screens/onboarding/AgeGateScreen.tsx`) is
  the first screen post-Welcome for any new account.
- Minor accounts get the full parental-consent flow per ADR-0011
  (Stripe-only at launch) before any biometric or behavioural data
  is captured.
- The consent matrix is enforced server-side: any data category not
  consented to is filtered at write time (athlete events fail closed,
  not open).
- The minor-specific data-retention policy
  (`docs/compliance/data-classification.md`) is enforced via the
  retention reaper job — Phase 1 adds the job (it doesn't exist yet);
  the table schema does.
- Right-to-erasure (PR #84 / #85) is exercised end-to-end as a Phase-1
  release gate, including video-asset crypto-shred and ML training
  set provenance audit.
- Legal-counsel sign-off on the EN + AR consent copy + privacy notice
  is a hard Phase-1 release gate (workstream L per the
  production-build plan).
- The Google Play Data Safety form (ADR-0013) discloses the minor
  data flows accurately.

## Consequences

**Positive.**
- The Egypt pilot's junior squad is supported on day one.
- The COPPA / GDPR-K / PDPL compliance posture is built into the
  product DNA rather than retrofitted; retrofitting youth compliance
  to an adults-only product is famously expensive (data already
  collected without consent has to be purged).
- The youth-sports diagnostic-coaching segment is a strong
  differentiator versus generic adult-aimed sport-tech products.

**Negative.**
- Legal sign-off becomes a launch-blocking gate that we don't
  control unilaterally (the lawyer can take a week).
- Stripe must be live at GA (ADR-0011), which adds one more
  must-have integration before launch.
- The retention reaper job is new code in Phase 1 (worked into
  workstream G).
- Any future feature has to ask "does this work for a 12-year-old's
  consent matrix?" before it ships — a permanent design tax.

## Alternatives considered

- **Adults-only at GA, minors in Phase 2** — would unblock GA by ~4
  weeks but excludes the design-partner's primary cohort. Rejected.
- **Ship minor UI but flag-gate behind "coming soon"** — would create
  a worse user-experience than not shipping it (parents would sign
  up and bounce) and would still require all the compliance work
  before the flag flips. Rejected as worst-of-both.
- **Geo-fence minors to Egypt only at GA** — operationally awkward
  (consent age varies per EU country, COPPA only applies in US) and
  delivers no clean simplification. Rejected.

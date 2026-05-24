# ADR-0011: Verifiable Parental Consent at Launch = Stripe Card Only

**Status:** Accepted · **Date:** 2026-05-24 · **Owner:** Compliance lead

## Context

`docs/compliance/parental-consent-flow.md` §3 enumerates four COPPA
"verifiable parental consent" methods backed by the mobile UI in
`aimvision-mobile/src/screens/onboarding/ParentalConsentScreen.tsx`:
paper-PDF + ID, credit-card verification, email + ID, video call.
All four UI methods exist; **none** is wired to a real verification
backend, and the `/auth/parental-consent` endpoint itself is not
implemented.

Per ADR-0015 we ship full minor-athlete support in Phase 1, which
means at least one verifiable method must be live for GA. The four
methods differ on automation, cost, and federation acceptability:

|Method|Setup work|Cost / consent|Provider example|
|---|---|---|---|
|Card verification|Days|~$0.30 (Stripe refunds the auth)|Stripe (COPPA §312.5(b)(2)(ii))|
|ID verification|Weeks|$1.50–$3.50|Veriff / Persona|
|Video call|Weeks + ops|$0.50+ per call|Twilio Video / Daily|
|Paper PDF + ID|Days code + ongoing review queue|Free + human review hours|n/a (LiveOps)|

Phase 1 also constrains us to the on-prem-first GA path (ADR-0012);
every verification provider is a SaaS but the *integration cost* (lift
of wiring it up + per-federation procurement review of the data flow)
is what we want to minimize.

## Decision

**Stripe card verification is the only active parental-consent method
in Phase 1.** Specifically:

- The mobile UI keeps all four method buttons but Phase-1 builds only
  surface the card path; the other three are gated off behind a
  runtime flag (`consent.methods.paper_pdf`, `…email_id`,
  `…video_call` → all `false`).
- The backend `/auth/parental-consent` endpoint implements the Stripe
  Setup Intent + immediate refund flow per COPPA §312.5(b)(2)(ii):
  1. Mobile collects the parent's card via Stripe Elements (PCI scope
     stays with Stripe).
  2. Backend creates a Stripe Setup Intent (no charge) and verifies
     `card.cvc_check = 'pass'` + a $1 auth + immediate refund.
  3. On success, write a row to a new `consent_records` table
     (parental_email, child_account_id, method='stripe',
     stripe_intent_id, verified_at, ip_hash, ua_hash) — the audit
     ledger.
- The other three method routes return 410 Gone with a "method
  temporarily unavailable" payload. Their backend handlers + provider
  integrations are deferred to a Phase-2 enhancement.

## Consequences

**Positive.**
- Smallest integration surface → fastest path to legal GA with minor
  support.
- Stripe is widely understood by federation procurement reviewers; no
  novel data-flow disclosure required.
- Phase 1 doesn't take a dependency on Veriff / DocuSign / Twilio
  contracts.
- All four UI screens are kept (no UI work to throw away) and the
  documented data-flow promises remain accurate; we just announce
  fewer methods at launch.

**Negative.**
- Parents without a credit card can't onboard a minor in Phase 1.
  In Egypt this is a real fraction of the addressable market; the
  Egypt pilot venue (ADR-0016) is an elite-federation context where
  this is less load-bearing than in a Solo-tier club rollout.
- Stripe's per-country availability matters. Egypt is supported (as
  of 2024). Other launch geographies will need spot-checks.
- COPPA permits card verification but legal counsel must sign off on
  the specific flow (workstream L is a Phase-1 gate per ADR-0015).

**Phase-2 trigger.** When > 10 % of attempted consents fail because
the parent has no card, enable Veriff (ID) as the second active
method. When a federation contractually requires wet-signed paper
consent, enable the paper-PDF + DocuSign path.

## Alternatives considered

- **All four methods at launch** — Phase-1 scope explosion (3 more
  vendor contracts, 3 more data-flow reviews). Rejected.
- **Email + ID only** — cheaper than card but ID review is human-in-loop
  ops we don't have a team for in Phase 1.
- **Defer minors entirely to a post-GA wave** — explicitly rejected
  by ADR-0015; the youth-sports compliance moat is the differentiator.
- **Build the consent flow without verification (just email
  acknowledgement)** — does *not* meet COPPA §312.5; rejected.

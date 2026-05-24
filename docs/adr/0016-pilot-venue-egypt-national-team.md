# ADR-0016: Phase-3 Pilot Venue = Egypt National Team Facility

**Status:** Accepted · **Date:** 2026-05-24 · **Owner:** Founder/CEO

## Context

The V2 sprint plan identifies the Egypt National Team as the
design-partner customer; CLAUDE.md anchors this in the project header.
The Phase-3 pilot of the production-build plan needs a venue where
the full stack runs end-to-end with real athletes, real clays, real
ranges, and a real coach using the coaching outputs to change athlete
behaviour. Candidate venues considered:

- **Egypt National Team facility** (Cairo) — design partner; existing
  relationship; junior + senior squads; competitive coaching context;
  on-prem deploy already aligned with their procurement model.
- **Cairo Shooting Club** (the "default" assumption in the original
  V2 plan) — broader club setting; less tightly defined coach + athlete
  cohort; useful as a Phase-2 club-tier validation but not as a
  Phase-3 elite-feedback loop.
- **Western club partner (US/UK)** — would diversify regulatory
  exposure but spreads pilot coordination across time zones and
  requires shipping the consent flow + payment flow in a new
  jurisdiction simultaneously with the pilot.

The pilot's purpose is to: validate the full capture → upload →
shot-detection → diagnostic-chip → coaching-note loop end-to-end with
a coach whose feedback is unfiltered; surface the operational rough
edges of the on-prem appliance (ADR-0012); and stress-test the
parental-consent + minor-athlete flow (ADR-0011, ADR-0015) with the
junior squad.

## Decision

**The Phase-3 pilot runs at the Egypt National Team facility.** The
Cairo Shooting Club is downgraded to a Phase-2 club-tier reference
target.

Concretely:

- The on-prem federation appliance is installed at the National Team
  facility, on their network, with their procurement / IT team in
  the loop. The 30-min installer target from ADR-0005 is exercised
  for real.
- The senior squad coach is the primary feedback channel for the
  coaching-note format, diagnostic taxonomy, and the
  shot-event-detail UI.
- The junior squad is the primary feedback channel for the parental
  consent + minor data-handling flows, and runs against the
  AR-localised mobile build.
- The Egypt PDPL action plan (`docs/compliance/egypt-pdpl-action-plan.md`)
  must be at "Active" status before the pilot starts; it is a hard
  Phase-3 entry gate.
- Pilot success criteria, week-to-week KPI cadence, and the "what
  would make us pull the pilot" criteria are documented in the
  production-build plan §11 (Phase 3).

## Consequences

**Positive.**

- The pilot is run with the design-partner cohort the platform was
  shaped for — feedback loops back to the right product instincts.
- One country, one timezone, one regulatory regime (PDPL) for the
  pilot — reduces operational surface during the high-noise pilot
  weeks.
- The on-prem appliance is exercised at a federation that's the exact
  archetype of the GA buyer (ADR-0012). Lessons translate directly.
- The junior squad provides the minor-cohort signal we need to
  validate ADR-0011 + ADR-0015 with real users.

**Negative.**

- Single-venue pilot does not surface region-specific bugs (lighting,
  ambient audio profile, network conditions of a US/UK range). We
  accept this as a known Phase-2 question: the second pilot venue,
  intentionally chosen to be different (climate, range layout,
  regulatory regime), is a Phase-2 entry condition.
- Logistical concentration risk: the founder needs to be physically
  on-site during the first week. Plan for at least one on-site
  presence per week through Phase 3.
- Egypt's electrical / network reliability profile must be
  characterised; the on-prem appliance needs a UPS spec in the
  bill-of-materials.

## Alternatives considered

- **Cairo Shooting Club (default in earlier docs)** — useful Phase-2
  validation venue but not the right Phase-3 elite-feedback context.
- **Western club partner** — geographic diversification at the cost
  of pilot coherence. Defer to Phase 2.
- **Multi-venue Phase-3 pilot** — too many unknowns to land
  simultaneously. The single-venue pilot keeps the feedback signal
  clean.

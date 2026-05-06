# Parental & Minor Consent Flow — AIMVISION

**Status:** Working draft for counsel refinement.
**Authority:** GDPR Art. 8; UK Children's Code (Standards 1–15); US COPPA (15 USC §§ 6501–6506; 16 CFR Part 312); Egypt PDPL (Law 151/2020) and Ministry of Youth and Sports authorization where applicable; ICO age-appropriate design guidance.
**Owner:** DPO (once appointed) + Product Lead.
**Implementation target:** Sprint 3 (before any minor data collection).

> Every legal-determination point is tagged `[CONFIRM WITH COUNSEL]`.

---

## 1. Why this matters

AIMVISION processes biometric data (pose keypoints), audio (potentially biometric voice characteristics), and optionally health data of athletes including **minors at federation programs (Egypt junior team and successor cohorts)**. The combined regulatory stack:

- **GDPR Art. 8** — information-society services offered to children require either (a) child is at age of consent in the relevant Member State (13–16, country-dependent) and gives consent themselves, or (b) parental consent is obtained and verifiable.
- **GDPR Art. 9** — biometric and health data require explicit consent; for minors, parental.
- **UK Children's Code** — the ICO expects high-privacy defaults, age-appropriate design, parental controls, and DPIA evidence (Standards 1–15).
- **US COPPA Sec. 312.5** — verifiable parental consent before collection of personal information from children under 13. AIMVISION's pose + video processing brings it well within COPPA scope when the user is under 13.
- **Egypt PDPL** — sensitive-data processing of minors requires guardian consent; for federation programs, additional Ministry of Youth and Sports authorization is anticipated `[CONFIRM WITH COUNSEL]`.
- **Image-rights and publicity laws** — vary by jurisdiction; minor likeness in marketing has separate, stricter requirements.

A weak consent flow is the single most likely source of regulator action. **A checkbox is insufficient.** This document specifies the architecture to satisfy the strictest applicable rule per data subject.

---

## 2. Age gate

Implementation: Sprint 3, before first minor capture.

**Date of Birth, not age, is collected.** DOB allows AIMVISION to:

- Branch flow correctly per current jurisdiction's age threshold.
- Schedule auto-prompt when the minor reaches majority.
- Detect age-misrepresentation downstream (e.g., HealthKit metadata mismatch).

### 2.1 Branching logic

```
collect DOB
collect country (used for jurisdiction-specific age threshold)
compute age + jurisdiction

if age >= 18:
    → standard adult flow (consent for Art. 9 categories; granular toggles)

elif 13 <= age < 18:
    → parental-consent path:
        1. block minor's account creation pending parent linkage
        2. collect parent contact email
        3. send parent verifiable-consent invitation (see §3)
        4. on parent grant, create linked child account with default high-privacy settings
        5. minor account is "supervised" — parent visibility into reports + scope

elif age < 13:
    → enhanced flow (US COPPA §312.5; UK Children's Code default high-privacy):
        1. mandatory verifiable parental consent (gold standard methods only)
        2. parent retains all controls
        3. minor account only renders age-appropriate UI; no engagement-maximizing nudges
        4. ML training, marketing, geolocation, and analytics shared with third parties default OFF and cannot be flipped on without re-consent

else:
    → reject (DOB malformed)
```

Country-of-residence determines exact thresholds (e.g., Germany requires consent at 16 under Art. 8; Spain at 14; UK at 13; Egypt's PDPL provides for guardian consent across all minors `[CONFIRM WITH COUNSEL]`).

### 2.2 Tamper-resistance

- DOB cannot be self-edited after account creation; change requires support ticket + identity verification.
- "Forgot to add my child? Use the Parent flow" link from anywhere in the app.
- Misrepresentation telemetry: if HealthKit DOB or wearable account differs from stored DOB by more than ~12 months, account is flagged for review.

---

## 3. Verifiable parental consent options

The four supported methods, ranked by friction × strength. All are auditable; single-checkbox is **rejected**.

### 3.1 Gold standard — signed paper consent + photo of guardian government ID + manual review

- **Method:** parent downloads a PDF, prints, signs, photographs along with their government ID, uploads via secure link emailed to a verified parent email. AIMVISION compliance reviewer manually checks ID-name matches signed-name and that ID is not visibly fraudulent. ID image is **not retained** beyond verification — verification result + redacted ID hash stored only.
- **Strength:** highest; satisfies COPPA §312.5(b)(2)(i) "signed consent form by mail or fax" extension and Egypt PDPL guardian-consent expectations.
- **Friction:** highest. Used for federation programs and for any under-13 user.
- **Retention of ID image:** purged within 7 days after review; only the verification flag and a hash are retained `[CONFIRM WITH COUNSEL]`.

### 3.2 Credit-card transaction (>$0.50, immediately refunded)

- **Method:** parent enters their own credit-card details for a small charge (>$0.50) which is refunded immediately. The card-holder identity must match parent name; payment processor confirms transaction. COPPA §312.5(b)(2)(ii) explicitly permits this.
- **Strength:** strong; widely recognized COPPA-compliant.
- **Friction:** low; familiar payment flow.
- **Limitation:** does not verify guardianship per se, only that an adult cardholder authorized the consent. AIMVISION pairs this method with parent name on the account record and a self-attested guardian-of-this-minor declaration.
- **Use:** standard for under-13 US users where the gold-standard flow is too slow.

### 3.3 Signed PDF + email-with-ID match

- **Method:** parent receives PDF, signs digitally (e.g., DocuSign-style), returns from a verified email; parent email had been previously verified via double opt-in.
- **Strength:** medium-strong; aligns with COPPA §312.5(b)(2)(iii) "use of digital signature" channel.
- **Friction:** medium.
- **Use:** default for 13–17 users globally; not preferred for under-13 unless paired with credit-card or ID step.

### 3.4 Video verification call

- **Method:** parent joins a scheduled video call with AIMVISION compliance staff, presents government ID on camera, audibly confirms consent and minor identity.
- **Strength:** very strong.
- **Friction:** highest scheduling friction.
- **Use:** federation programs and high-risk cases (e.g., where flagged DOB or unusual metadata).

### 3.5 Rejected: single-checkbox / "I am the parent" attestation

Insufficient under all four legal frameworks. Never deployed alone.

---

## 4. Account model

A separate **Parent account** is created. The minor's account is **linked to** the parent and supervised.

### 4.1 Schema (logical)

- `parent_account` — Parent's identity, verified email, payment method (if applicable).
- `child_account` — Minor's identity (name + DOB), `parent_id` FK, `consent_state` JSON.
- `consent_grant` — append-only record of every grant/revoke per (data_category × purpose × version).

### 4.2 Parent rights and controls

- **Read access** to all child reports (sessions, longitudinal trends, LLM coaching notes).
- **Write access** to consent toggles per category and per purpose (see §4.3).
- **Deletion control** — parent can request erasure on behalf of child at any time; pipeline per `right-to-erasure-architecture.md`.
- **Scope changes** — adding a new processor (e.g., new wearable) prompts parent re-consent; minor cannot self-add high-impact integrations.
- **Notifications** — parent receives summary of activity, of new data categories enabled, of incidents.

### 4.3 Granular consent matrix (per child)

Consent is **never bundled.** Each cell is independently grantable / revocable.

| Data category                                          | Coaching (in-app) | Marketing     | ML training   | Validity study |
| ------------------------------------------------------ | ----------------- | ------------- | ------------- | -------------- |
| Video                                                  | Off / On          | Off (default) | Off (default) | Off (default)  |
| Audio                                                  | Off / On          | Off (default) | Off (default) | Off (default)  |
| Pose keypoints                                         | Off / On          | Off (default) | Off (default) | Off (default)  |
| Voice notes                                            | Off / On          | Off (default) | Off (default) | Off (default)  |
| Performance metrics                                    | Off / On          | Off (default) | Off (default) | Off (default)  |
| Wearable / HealthKit                                   | Off (default)     | Off (default) | Off (default) | Off (default)  |
| LLM coaching notes (the LLM sees pseudonymized inputs) | Off / On          | Off (default) | Off (default) | Off (default)  |

Defaults for minors: high-privacy. Coaching and post-session analysis only after explicit grant per category. Marketing, ML training, and validity-study toggles **default off and cannot be enabled without separate flow** (re-consent with explicit acknowledgement screens).

### 4.4 Federation overlay

For minors enrolled in a federation program (e.g., Egypt junior team), an additional federation-acknowledgement layer applies:

- Federation must be a **named recipient** in the consent record.
- Federation cannot expand scope; only AIMVISION (with parent re-consent) can.
- Federation export of cohort data requires k-anonymity threshold.
- Egypt: ministerial authorization captured before federation onboarding `[CONFIRM WITH COUNSEL]`.

---

## 5. Egypt-specific layer

Egypt PDPL requires guardian consent for processing of minors' personal data; sensitive-data processing has additional safeguards. For federation-administered programs (Egyptian junior shooting team), the path that is most defensible per current understanding:

1. **Guardian consent** captured per §3 gold-standard (signed paper + government ID + photo).
2. **Federation joint-controller agreement** under Art. 26 GDPR equivalent + PDPL.
3. **Ministry of Youth and Sports authorization** for the federation program — `[CONFIRM WITH COUNSEL]` Egyptian counsel to confirm exact instrument (memorandum, ministerial decree, federation-level approval).
4. **Bilingual consent** (Arabic + English); athlete-readable and guardian-readable variants; both reviewed by Egyptian counsel and EU counsel.
5. **In-region processing** for Egyptian athletes (AWS me-south-1 or on-prem federation hardware); cross-border transfers per PDPC permits.

A federation program cannot be onboarded into AIMVISION until items 1–5 are satisfied for every enrolled minor.

---

## 6. Re-consent triggers

Consent is **never indefinite.** Re-consent is required at:

- **Every new data category.** If AIMVISION adds, e.g., gaze tracking or grip-pressure IMU, consent for that new category is collected fresh; existing consents remain.
- **Every new purpose.** If AIMVISION wants to use a category for a new purpose (e.g., pose data for cross-federation cohort analytics where it was only consented for individual coaching), fresh consent.
- **Every annual review.** All consents are revisited by parent + minor (age-appropriate UI for minor) at the anniversary of grant.
- **Material change to the privacy notice or sub-processor list.** Parent informed; consent revisited where the change is more than incidental.
- **Transition to majority** — see §7.

---

## 7. Auto-deletion at majority

When the minor turns 18 (or earlier majority age in jurisdiction `[CONFIRM WITH COUNSEL]`), the system enforces:

1. **Day -30**: notify parent and athlete of upcoming transition.
2. **Day 0** (athlete turns 18): mandatory re-consent prompt to the (now-adult) athlete. Account placed in "transition" mode.
   - In transition mode, no new data is processed except what the athlete actively initiates.
   - LLM coaching, ML-training, marketing flags reset to default-off.
3. **Day 0–90**: athlete may complete re-consent on their own behalf. Parent's controls cease at Day 0; parent's read access also ceases at Day 0 (or earlier if athlete requests).
4. **Day 90 without re-consent**: account is auto-purged via the erasure pipeline. Communications log retained per audit-log retention; all athlete data tombstoned and crypto-shredded per `right-to-erasure-architecture.md`.
5. The retention schedule documents this 90-day window explicitly.

Additional triggers analogous to the majority transition:

- Athlete leaves federation junior program (transition mode, prompt for new consent context).
- Account inactivity > 24 months (re-consent or auto-purge).

---

## 8. Marketing exclusion

**Minors never appear in marketing assets** (case study, screenshots, promo videos, sales decks, web assets) without:

1. A separate, jurisdiction-valid **publicity-rights release** signed by the guardian (and where applicable, by the federation and the minor for ascertainment purposes).
2. A documented determination that the use is appropriate and would not harm the minor's interests.
3. Default visual treatment: **blur or exclude.** Even with release, AIMVISION's preferred posture is to blur faces and remove identifying detail.
4. Geographic validity: a release valid in jurisdiction A is not assumed to authorize use in jurisdiction B; counsel sign-off per intended audience.
5. Revocation: if release is revoked, takedown SLA `[CONFIRM WITH COUNSEL]` (recommend ≤30 days). All cached / syndicated copies traced and removed.

The default for the Sprint 22 Egypt case study is **adults-only**; minors blurred or excluded; no exceptions absent counsel review.

---

## 9. UI flows (wireframe-level)

### 9.1 Parent-onboarding screen

- Headline: "You're setting up an AIMVISION account for a young athlete."
- Step 1 — verify your identity: email + (one of §3 methods).
- Step 2 — add child: name + DOB + relationship.
- Step 3 — review default settings: explicit list of what is collected, why, and the high-privacy defaults; coaching toggles reach in here.
- Step 4 — decide on optional categories: marketing, ML training, validity study — each with plain-language description and example consequences. Each is its own affirmative grant.
- Step 5 — sign. The parent is shown a generated summary of their grants and signs (digital signature or, for gold-standard, paper-signed PDF).
- Step 6 — confirmation. Email receipt to parent. Audit log entry.

### 9.2 Child-onboarding screen (parent-supervised)

- Age-appropriate language; no marketing nudges; no engagement-loop dark patterns.
- Headline: "Welcome to AIMVISION! Your parent set up your account."
- Step 1 — confirm name and DOB with parent present.
- Step 2 — explain in plain language: "We'll watch your shooting and help your coach give you feedback. We will not show your videos to anyone else without your parent saying yes."
- Step 3 — show what is on / off, as set by parent.
- Step 4 — child confirms participation (assent — distinct from legal consent which the parent gave). Audit log records assent.

### 9.3 Consent-grant screen

- Per-category checkboxes (not a single mega-toggle).
- Each checkbox is paired with: (a) plain description of what is processed; (b) named recipients; (c) retention; (d) link to fuller text.
- Defaults match current state (off for marketing/ML/validity for minors; on for in-app coaching only after explicit grant).
- "Save" produces a versioned consent record with timestamp, IP, and version hash.
- Parent receives email confirmation summarizing changes.

### 9.4 Consent-revoke screen

- Reachable from at most two taps from the home screen.
- Per-category and per-purpose toggles mirror the grant screen.
- Revocation effect: immediate stop of new processing in that scope; downstream effects (e.g., LLM-coaching prompts no longer built from voice notes) are explained.
- For ML-training revocation: explain "your data will be excluded from future model training; existing models cannot fully unlearn" (see `right-to-erasure-architecture.md` §9 limitations).
- Revocation does not require justification.
- Revocation produces an audit-log entry and triggers downstream pipelines (exclusion list, marketing-asset takedown if applicable).

### 9.5 Deletion-confirmation screen

- Plain summary of what will happen: "All your sessions, videos, audio, pose data, and coaching notes will be deleted from AIMVISION within 30 days. Some records (audit logs, billing, consent records) will be kept for legal reasons for up to 7 years and then deleted. Your data may already have been used to train improvements to AIMVISION; we cannot remove your data from models that are already trained, but we will not use your data in any future training and we will retire affected models over time."
- Cooldown / undo within 7 days (per GDPR practical-rights guidance for accidental deletion `[CONFIRM WITH COUNSEL]`).
- Final confirmation requires re-authentication.
- Audit-log entry; ticket created in erasure pipeline.

---

## 10. Audit trail

Every consent event is captured to the audit log per `docs/security/audit-logging-spec.md` (planned). Minimum fields:

- `event_type` — one of: `consent_grant`, `consent_revoke`, `consent_version_change`, `assent_recorded` (child), `parental_method_used` (e.g., paper-id-review, credit-card, signed-pdf, video-call), `re_consent_prompt_shown`, `auto_purge_due`.
- `data_subject_id` — pseudonymous athlete or minor ID.
- `parent_subject_id` — when applicable.
- `category × purpose × version` — exact tuple changed.
- `actor_id` — who performed the action (parent / athlete / compliance staff for paper-ID review).
- `evidence_pointer` — hash + storage URI for signed PDF / payment-method verification reference / video-call recording reference where retained.
- `timestamp`, `ip_address`, `user_agent`, `app_build`.
- `event_chain_hash` — links to previous audit event for integrity.

Audit log is append-only and integrity-protected; hash chain plus periodic anchor to write-once storage. Retention 24 months minimum, longer for legal hold; consent records retained beyond audit retention per RP-023 in `ropa-template.md`.

---

## 11. Implementation checklist (Sprint 3)

- [ ] DOB + country-of-residence collected at signup; flow branches on age and jurisdiction.
- [ ] Parent-account flow with §3 verifiable-consent methods (at minimum signed-PDF + credit-card; gold-standard for federation/under-13).
- [ ] Granular consent matrix (§4.3) implemented with high-privacy defaults for minors.
- [ ] Egypt overlay with bilingual consent, federation joint-controller doc, ministerial-authorization placeholder, in-region processing.
- [ ] Re-consent triggers wired (annual, new category, new purpose, sub-processor change).
- [ ] Majority-transition automation (Day -30 / Day 0 / Day 90).
- [ ] Marketing exclusion default; takedown SLA wired; release-record (RP-025).
- [ ] UI flows reviewed with at least two parents and two minor athletes (qualitative usability check).
- [ ] Audit log emits all events specified in §10.
- [ ] DPO sign-off; counsel sign-off (`[CONFIRM WITH COUNSEL]` per row).

---

## Changelog

- v0.1 (Sprint 0): initial draft.

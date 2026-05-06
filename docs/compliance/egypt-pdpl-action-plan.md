# Egypt PDPL Action Plan — AIMVISION

**Status:** Working draft for counsel refinement.
**Authority:** Egyptian Personal Data Protection Law, Law No. 151 of 2020 ("PDPL"), Personal Data Protection Center (PDPC), and supporting executive regulations as enacted `[CONFIRM WITH COUNSEL]`.
**Owner:** DPO (once appointed) + Egyptian counsel + Compliance Lead.
**Driver:** Sprint 5 first Egypt capture is the binding deadline. Nothing collected from Egyptian data subjects before items in §3 are complete.

> Every legal-determination point is tagged `[CONFIRM WITH COUNSEL]`. Penalties are statutory and personal — including imprisonment of officers — so this plan is high-priority and counsel-led.

---

## 1. PDPL primer

The Egyptian PDPL came into force in 2020 and is administered by the **Personal Data Protection Center (PDPC)**. The PDPC is the regulator, the licensor, and the cross-border-transfer permitting authority. Headline articles relevant to AIMVISION:

- **Article 1 — Definitions.** Personal data, sensitive personal data, controller, processor, electronic processing. Sensitive data includes biometric, genetic, health, religious, political, and minor-related data — AIMVISION's pose, voice, and (optional) wearable streams plausibly fall within "sensitive" `[CONFIRM WITH COUNSEL]`.
- **Article 4 — Licensing.** Controllers and processors of personal data require a license / permit from PDPC for certain activities, especially involving sensitive data and minors. Operating without the requisite license is an enforcement target.
- **Article 8 — Data Protection Officer.** Sensitive-data controllers must appoint a DPO; the DPO must be locally accessible and capable of liaising with PDPC.
- **Article 9 — Special / sensitive data.** Heightened processing rules: explicit, separate consent; purpose-limitation; restricted disclosure; documentation requirements.
- **Articles 14–15 — Cross-border transfers.** Cross-border transfer of personal data requires PDPC permit; standard of protection in destination must be at least equivalent; permits are issued bidirectionally.
- **Article 19 — Special-data rules.** Detailed obligations for processing of sensitive data: written-consent requirements, accountability, narrow lawful bases.
- **Other articles** — breach notification, individual rights (access, rectification, erasure, objection), minors' rights, retention limits, contractual obligations between controllers and processors.

Penalties (per current understanding `[CONFIRM WITH COUNSEL]`): fines from EGP 100,000 to EGP 5,000,000 for various offences and **imprisonment** for responsible officers in egregious cases. Practical effect: regulator non-compliance risk is **personal** to AIMVISION officers, not merely corporate.

---

## 2. Why AIMVISION triggers the high-tier requirements

PDPL contains tiered obligations. AIMVISION sits in the most demanding tier because:

1. **Biometric data of identified individuals.** Pose keypoints linked to athlete identity are biometric `[CONFIRM WITH COUNSEL]`. Voice recordings carry biometric voiceprint risk. Either alone is enough.
2. **Health data.** Optional wearable integration introduces health data even if off by default. Health is sensitive under PDPL.
3. **Minor athletes.** Egypt junior team and any future youth program enrolls under-18 athletes. Minor-protection rules trigger guardian-consent and additional procedural safeguards.
4. **Cross-border transfers in both directions.** Egyptian data flowing to Railway/AWS/Sentry abroad is outbound; coaching artifacts produced abroad and returning is inbound. Permits required both ways.
5. **Federation joint-controllership.** Egyptian Federation is a joint controller — joint controllers each bear primary obligations.
6. **Public-interest framing.** Federation programs may invoke government / public-interest framing — that does not relax PDPL; it sometimes intensifies recordkeeping.

Net effect: AIMVISION must register, license, appoint a DPO, file cross-border permits, and conduct DPIAs **before** the first Egyptian session capture. Skipping any item halts the Egypt pilot and risks officer-level enforcement.

---

## 3. Required actions before Sprint 5 (first Egypt capture)

The following items must be **complete and evidenced** before any data is captured from Egyptian data subjects.

### 3.1 PDPC registration and processor / controller license — Sprint 1 kickoff

- File registration of AIMVISION (and the local entity, if one is required `[CONFIRM WITH COUNSEL]`) with PDPC.
- Apply for processor / controller license appropriate to the sensitivity tier.
- DPIA (per `dpia-outline.md`) included in dossier.
- Allow ≥6–12 weeks for review per current PDPC capacity `[CONFIRM WITH COUNSEL]`. Start in Sprint 1.
- **Owner:** Egyptian counsel coordinating filing; AIMVISION Compliance Lead supplying the technical dossier.

### 3.2 Appoint locally-accessible DPO — Sprint 1

- DPO **separate from CTO** (Art. 38(6) GDPR equivalent conflict-of-interest). The cross-application principle applies under PDPL `[CONFIRM WITH COUNSEL]`.
- Locally accessible to data subjects in Egypt — practical options: Egyptian-resident DPO; Egyptian-counsel-led DPO function; DPO-as-a-service firm with Cairo presence.
- Reporting line: directly to CEO.
- DPO scope letter signed and logged.
- **Owner:** CEO, with Egyptian counsel.

### 3.3 Cross-border transfer permits — Sprint 2

- Outbound permit: Egypt → EU (eu-central-1; processors there).
- Outbound permit: Egypt → US (Sentry, Stripe, possibly some legacy processors).
- Inbound permit: data flowing back to Egypt (e.g., reports, model artifacts) where personal data is included.
- Each permit accompanied by a **Transfer Impact Assessment (TIA)** documenting destination-country protections, supplementary measures (encryption, key control), and residual risk.
- **Owner:** Egyptian counsel + AIMVISION Compliance Lead.

### 3.4 Joint-controller agreement with Egyptian Federation — Sprint 1–2

- Formal Article 26 GDPR equivalent + PDPL joint-controller arrangement between AIMVISION and the Egyptian Federation.
- Allocates responsibilities: who handles DSARs, who notifies breaches, who controls retention, who controls scope changes.
- Mandates that federation cannot unilaterally expand processing scope.
- Mandates specific minor-handling rules: no athlete deselection or sanction based on AIMVISION-derived metrics absent validity disclosure; no marketing use of minor likeness; ministerial-authorization-prerequisite for processing minor-cohort data `[CONFIRM WITH COUNSEL]`.
- **Owner:** Egyptian counsel drafting; CEO + federation officer signing.

### 3.5 DPIA finalized and filed — Sprint 2

- Finalize `dpia-outline.md` to a sign-off-ready document.
- Counsel sign-off per `[CONFIRM WITH COUNSEL]` rows.
- Submit relevant portions to PDPC as part of license dossier (Egypt expects a DPIA for sensitive-data tier `[CONFIRM WITH COUNSEL]`).
- **Owner:** DPO + Compliance Lead.

### 3.6 Athlete consent forms in Arabic + English — Sprint 1–3

- Translation by qualified legal translator (not machine).
- Reviewed by Egyptian counsel for PDPL conformity, by EU counsel for GDPR conformity, and by UK counsel for Children's-Code-influenced minors language.
- Plain-language readable variants for both adult athletes and parents.
- Athlete-readable child variant (age-appropriate) per UK Children's Code Standard 4.
- Versioned and stored against each consent record (RP-023).
- **Owner:** Compliance Lead + Egyptian counsel + EU counsel + UK counsel.

### 3.7 Parental + ministerial consent for junior team — Sprint 3

- Parental consent flow per `parental-consent-flow.md`.
- Ministry of Youth and Sports authorization captured for the federation junior program — exact instrument per `[CONFIRM WITH COUNSEL]`. Possibilities include:
  - A federation-level memorandum of understanding referencing AIMVISION as approved technology vendor.
  - A ministerial decree or letter authorizing the program with AIMVISION involved.
  - A program-specific consent layered on top of federation's general consent.
- Authorization filed with PDPC dossier.
- **Owner:** Federation Operations + Egyptian counsel.

### 3.8 Data residency commitment — Sprint 2

- Egyptian-athlete data held **in-region**.
- Two viable options:
  - **AWS me-south-1 (Bahrain)** — closest AWS region; documented as PDPL-compatible if accompanied by SCCs and PDPC permit `[CONFIRM WITH COUNSEL]`. Latency to Egypt is acceptable.
  - **On-prem federation hardware** — federation-hosted compute and storage with AIMVISION software stack, no cloud egress for personal data; aligns with `06-security-engineer.md` "Federation on-prem isolation" recommendation.
- Decision documented in an ADR; default for Egypt junior program is on-prem federation hardware with cloud-based read-only synthetic-aggregate sync `[CONFIRM WITH COUNSEL]`.
- **Owner:** Eng Platform Lead + DPO.

---

## 4. Ongoing PDPL obligations

Once the program is live, AIMVISION must maintain the following continuous obligations:

### 4.1 Annual report to PDPC

- Annual filing with PDPC summarizing processing activities, sensitive-data volumes, cross-border transfers, breaches, DSAR statistics.
- Filed by DPO under the local license `[CONFIRM WITH COUNSEL]`.

### 4.2 Breach notification within 72 hours

- Notification window for breaches affecting Egyptian data subjects: PDPC notification within 72 hours of awareness. Affected subjects notified per legal requirements.
- Internal breach-detection process must surface breaches to DPO within 24 hours; DPO assesses notifiability and files.
- Breach-handling runbook in `docs/security/incident-response.md` (planned).

### 4.3 DPO accessibility

- DPO must be reachable by Egyptian data subjects in Arabic and English.
- Dedicated email + Egyptian phone line.
- Response to data-subject inquiries within statutory deadlines (per GDPR-mirroring window of 30 days, possibly shorter under PDPL `[CONFIRM WITH COUNSEL]`).

### 4.4 Retention schedule

- Documented per `data-classification.md` and per `ropa-template.md`.
- Retention enforcement automated where possible.

### 4.5 Individual rights implementation

PDPL guarantees individuals the rights to:

- **Access** — DSAR fulfillment via RP-018.
- **Rectification** — in-app edit + ticketed process.
- **Erasure** — RP-019; per `right-to-erasure-architecture.md`.
- **Portability** — structured export (JSON + raw video / pose archive).
- **Objection** — to specific processing where lawful basis is legitimate-interest; opt-out flow.

A **DSAR self-service portal** by Sprint 17 satisfies most of these via automation. Manual review for edge cases.

### 4.6 Records of processing

- RoPA per `ropa-template.md` maintained current; produced on PDPC request within statutory window.

### 4.7 Sub-processor chain governance

- Every sub-processor under signed DPA.
- Sub-processor changes disclosed to data subjects (via privacy notice + email for material changes).
- Onward transfers approved per PDPC permit.

### 4.8 Training

- Annual mandatory training for all staff with access to Egyptian personal data, in Arabic and English.
- Records of training completion retained.

---

## 5. Penalty exposure

Per current understanding (figures are statutory and may be adjusted by executive regulation `[CONFIRM WITH COUNSEL]`):

- **Fines:** EGP 100,000 to EGP 5,000,000 depending on the offence, with the higher tier applying to sensitive data and minor-data violations.
- **Imprisonment of officers:** for severe violations involving sensitive data, fraud, or willful non-compliance — typically several months to years `[CONFIRM WITH COUNSEL]`.
- **Operational halt:** PDPC may issue a cease-and-desist that halts processing, effectively shutting the Egypt pilot.
- **Reputational:** federation procurement worldwide will see PDPC action; SOC 2 / ISO 27001 auditors will probe.

Risk-mitigation posture: front-load all §3 items; treat penalty exposure as material to the company's existence, not a back-office compliance cost.

---

## 6. Counsel engagement plan

AIMVISION engages **three external counsel** plus an internal compliance/DPO function:

### 6.1 Egyptian PDPL counsel

- Cairo-based firm with active PDPL practice and experience filing PDPC license applications.
- Scope: PDPC filings, DPIA review per Egyptian standard, joint-controller agreements, ministerial-authorization advice, ongoing PDPC liaison.
- Engagement target: Sprint 1.
- Specific firm names: **omitted pending counsel-side recommendations** `[CONFIRM WITH COUNSEL]`. Compliance Lead to gather references from federation legal counsel, regional bar association directories, and at least two existing PDPC-filed clients.

### 6.2 EU privacy counsel

- EU-firm with cross-border (Article 26 / 28 / 46) expertise and ideally familiarity with sport-tech / wearable data.
- Scope: GDPR DPIA review, joint-controller drafting, SCC application, lead-supervisory-authority strategy, breach-notification advice.
- Engagement target: Sprint 1.
- `[CONFIRM WITH COUNSEL]` for specific firm.

### 6.3 UK Children's Code counsel

- UK-firm with active engagement on the ICO's Age-Appropriate Design Code.
- Scope: Standards 1–15 implementation review, age-gate design review, parental-consent flow review, ICO communications.
- Engagement target: Sprint 1.
- `[CONFIRM WITH COUNSEL]` for specific firm.

### 6.4 US COPPA counsel

- Optional but recommended given expected US user base.
- Scope: COPPA §312.5 verifiable-consent method review, FTC interactions if any, COPPA Safe Harbor program evaluation.
- Engagement target: Sprint 2.

### 6.5 Coordination

- Compliance Lead is the single point of contact across all four firms.
- Joint review meeting once per quarter; consolidated counsel memo published internally.
- Where firms disagree, the **strictest** rule applies until resolved; documented as a finding.

### 6.6 Costs (planning estimate `[CONFIRM WITH COUNSEL]`)

- Egyptian counsel: USD 30k–60k for initial filing + ongoing retainer.
- EU counsel: USD 40k–80k for DPIA / SCCs / joint-controller draft + retainer.
- UK counsel: USD 20k–40k.
- US counsel: USD 15k–30k.
- Buffer for unanticipated issues: 25%.

---

## 7. Sprint-by-sprint compliance milestones (Egypt-specific)

| Sprint | Milestone                                                                                                                                                                                   |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1      | Egyptian + EU + UK + US counsel engaged. PDPC registration filing initiated. DPO appointed.                                                                                                 |
| 2      | Cross-border transfer permits filed; TIAs drafted; joint-controller agreement with federation drafted; data-residency ADR signed; DPIA finalized; DPIA submitted with PDPC license dossier. |
| 3      | Bilingual consent forms reviewed by all counsel; parental-consent flow shipped; age gate live.                                                                                              |
| 4      | License application iterations with PDPC; joint-controller agreement signed with federation.                                                                                                |
| 5      | License in hand or PDPC has issued provisional approval; ministerial authorization in hand for junior program; **first Egypt capture authorized.**                                          |
| 6      | DSAR self-service path drafted; audit log live (per security review pull-forward).                                                                                                          |
| 8      | Audit log fully operational; DPA's signed with all sub-processors.                                                                                                                          |
| 17     | DSAR self-service shipped; erasure pipeline (per `right-to-erasure-architecture.md`) live.                                                                                                  |
| 22     | Marketing case study path open to **adults only** in Egypt; minors blurred or excluded.                                                                                                     |

If any Sprint-1–5 item slips, Sprint 5 capture slips. **Do not capture in Egypt without all green lights.**

---

## 8. Key risks specific to Egypt

| Risk                                                              | Mitigation                                                                                                                                |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| PDPC license review takes longer than 12 weeks                    | Start Sprint 1; provisional engagement with federation that doesn't depend on capture; counsel-led expediting where possible.             |
| Cross-border permit denied                                        | Fall back to fully on-prem federation deployment; AIMVISION cloud holds zero Egyptian personal data.                                      |
| Ministerial authorization unclear                                 | Egyptian counsel + federation legal officer to determine instrument; AIMVISION will not collect federation-program minor data without it. |
| PDPL executive regulations evolve                                 | Quarterly counsel review of regulatory updates; build flexibility into consent versioning and retention schedules.                        |
| Sub-processor (Sentry, Railway, AWS, Stripe) lacks PDPC-ready DPA | Engage processor-side legal early; renegotiate or substitute (e.g., self-host Sentry; AWS already has multi-region maturity).             |
| Officer-level penalty risk                                        | DPO + Compliance + Counsel sign every consent flow change; CEO briefed monthly; D&O insurance reviewed for compliance-officer coverage.   |

---

## Changelog

- v0.1 (Sprint 0): initial action plan drafted by Compliance Auditor.

# AIMVISION QR Check-In Token Cryptographic Specification

**Owner:** Security Engineer
**Status:** Draft v1.0 — must be ratified before Sprint 16 (cross-tier check-in)
**Source review:** `docs/reviews/06-security-engineer.md` §"QR Check-In Token Design"
**Related:** `docs/security/threat-model.md` §4.3, `docs/security/multi-tenant-isolation.md` §5, `docs/security/audit-logging-spec.md`

---

## 1. Problem Statement

A Solo subscriber arrives at a partner club. The club runs a session and produces a session video that the club's session-writer ingests. Without check-in, the video belongs entirely to the club tenant. The Solo user wants the parts of that session that depict *them* to flow into their own tenant as a personalized coaching report — without giving the club any read access to the Solo user's history (other sessions, prior coach annotations, ML training opt-ins, payment metadata, identity beyond first name).

This problem has two failure modes that traditional designs fall into:

1. **The "JWT-with-the-user's-identity" failure.** A naive implementation issues a session token to the club that has the Solo user's `sub` claim. Anyone holding that token can call `/users/{id}/sessions` or `/users/{id}/reports`. A compromised club dashboard becomes a complete read of every Solo user who ever checked in.
2. **The "shared symmetric secret" failure.** A naive implementation generates a per-club API key and lets the club write attribution events for any user. A compromised club can claim attribution for users who were never present. Audit log fills with bogus entries; detection is hard.

The design below avoids both. The token issued at check-in is **redeemable exactly once, by exactly one club, within 90 seconds**, and the redemption response is **a write-only attribution capability scoped to one session** — not a token that can read anything.

**Core invariant:** *Even a fully compromised club dashboard must not exfiltrate anything beyond the current session attribution.*

---

## 2. Token Format: PASETO v4.local

**PASETO v4.local** = XChaCha20-Poly1305 + BLAKE2b. Symmetric key in cloud KMS, never leaves the backend.

### Why not JWT

| JWT pitfall                                               | PASETO v4.local                                                                                                                |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `alg=none` and key-confusion attacks                      | No `alg` field. Versioned algorithm choice baked into the token version (`v4.local`).                                         |
| Asymmetric vs symmetric key confusion (RS256 vs HS256)    | One algorithm per version. v4.local is symmetric authenticated encryption only.                                                |
| Header is unauthenticated by some implementations         | All bytes are authenticated by the AEAD; no separate header trust boundary.                                                    |
| Algorithm-agility footguns                                | PASETO bumps version, not algorithm. Forward compatibility without negotiation.                                                |
| Bearer-token-in-URL leaks via referer / logs              | We do not put PASETO in URLs. QR is rendered, not redirected.                                                                  |
| Sprawling claim conventions                               | PASETO claims are a small, typed footprint we control end to end.                                                              |

We pick **v4.local** (symmetric) because the token is read and written only by our backend. The club never decrypts the token; it only relays the bytes.

### Why not a plain opaque random ID

We considered an opaque ID with all state in Redis. Rejected because (a) we still need a MAC-bound payload so the redemption endpoint can validate `purpose` and `allowed_club_ids` even on cold-cache failover; (b) PASETO gives us a typed, auditable claim set that survives Redis loss; (c) the encrypted body lets us bind purpose claims that we never want to round-trip through Redis.

---

## 3. Token Claims

PASETO v4.local encrypted body (CBOR-encoded for compactness; JSON for examples):

```json
{
  "athlete_id": "u_01HX2ZP4N0V8C7W3J6K9MQ5RTY",
  "purpose": "club_session_attribution_only",
  "iat": 1762371000,
  "exp": 1762371090,
  "jti": "01HX2ZP6X7Y8Z9A0B1C2D3E4F5",
  "nonce": "8d4f2a3b1e6c7d9f0a2b4c6e8f0a1b2c",
  "allowed_club_ids": [
    "c_01HV9R3E0M",
    "c_01HW1P8AKQ"
  ],
  "key_epoch": 7
}
```

Claim semantics:

- `athlete_id` — the Solo user's stable ID. Encrypted; never visible to the club.
- `purpose` — fixed string. Redemption endpoint refuses any non-matching value.
- `iat` — issued-at, seconds since epoch.
- `exp` — issued-at + 90s. Server-validated; clock skew tolerance ±5s.
- `jti` — random 128-bit token ID. Redis ledger key.
- `nonce` — additional 128-bit value for defense-in-depth against `jti` collisions; also used as part of channel-binding hash.
- `allowed_club_ids` — set of club IDs that the athlete pre-authorized to consume their tokens at this facility. Authorization is established during onboarding (see §15). Maximum set size: 8 (we resist a wandering athlete's set growing unbounded; if larger, the athlete is prompted to prune).
- `key_epoch` — the KMS key epoch used to derive the encryption key. Lets us roll the QR-token symmetric key without invalidating in-flight tokens.

The token has no `iss`/`aud` because we have one issuer and the audience is constrained by `allowed_club_ids`.

### 3.1 Token sizing

A typical token is ~220 bytes binary, base64-url ~300 chars. With the version + footer, the QR payload (see §4) is ~330 chars. This fits comfortably in a QR Code Version 13 (Error-Correction Level M), which renders cleanly at 5cm wide on a phone screen.

---

## 4. QR Payload Structure

The displayed QR encodes:

```
av1:<paseto>-<6digit>
```

- `av1:` — AIMVISION QR version 1 prefix.
- `<paseto>` — base64-url of the PASETO v4.local token.
- `-` — separator.
- `<6digit>` — a 6-digit numeric channel-binding code, derived as `BLAKE2b(jti || nonce || athlete_id || "channel_binding_v1")` truncated to 20 bits, mod 1,000,000, zero-padded.

The 6-digit code is **also displayed beneath the QR** on the athlete's phone. The redemption endpoint requires the club to submit *both* the PASETO bytes (as scanned) **and** the 6-digit code (as either typed by the club operator after the athlete reads it, or scanned together with the QR). If the QR was photographed from across the room and the photographer never heard the athlete speak, they have only the PASETO. The 6-digit gate forces an in-person interaction that an opportunistic photographer cannot satisfy.

For high-trust facilities the club may turn on "auto-bind" mode where the same QR encodes both — the photographer would still need to be physically present to capture it cleanly during the 90-second window. Auto-bind is an explicit per-facility setting; default is *separate channel-binding code*.

---

## 5. Issuance Flow

### 5.1 Endpoint

```
POST /v1/checkin/tokens
Authorization: Bearer <athlete_session_token>     # PASETO v4.public
X-Request-Id: <uuid>
Content-Type: application/json

{
  "facility_hint": "club:c_01HV9R3E0M"             # optional; lets the
                                                    # backend prune
                                                    # allowed_club_ids
                                                    # to the relevant set
}
```

### 5.2 Server-side

1. Authenticate the athlete via session token.
2. Look up the athlete's `allowed_club_ids` set from the `athlete_club_authorization` table.
3. If `facility_hint` provided and present in the set, narrow the token to that one club. This minimizes the blast radius if the QR is leaked.
4. Pull the per-tenant subkey from KMS. Subkey is HKDF-derived from the QR-token root key, with `info = "qr-checkin/" + tenant_id`. Key epoch is recorded.
5. Generate `jti` (16 random bytes from the OS CSPRNG), `nonce` (16 random bytes).
6. Build claims, encrypt as PASETO v4.local, base64-url encode.
7. Compute the 6-digit channel-binding code.
8. Emit audit event `checkin.token_issued` with `athlete_id`, `jti`, `allowed_club_ids`, `iat`, `exp`, `request_id`. (See `docs/security/audit-logging-spec.md` §2 event #14.)
9. Return `qr_payload` and `display_code` to the mobile app.

### 5.3 Rate limiting

- Per-athlete: ≤5 issuances per minute, ≤20 per hour, ≤100 per day. Hitting any of these surfaces a "slow down" UI; persistent abuse triggers an account anomaly review.
- Global: token-bucket sized to peak facility throughput (e.g. 1k QPS); breaches alert the on-call SRE.

### 5.4 Key management

- **Root key** lives in KMS, never leaves. We use envelope encryption: the root key wraps a per-tenant subkey, the subkey is what actually encrypts the PASETO body.
- **Rotation:** root key rotates every 90 days. Per-tenant subkeys are HKDF-derived per epoch and cached in memory only; in-flight tokens carry `key_epoch` so we can decrypt them with the right subkey for up to 24h after rotation. After 24h post-rotation, old subkeys are zeroized.
- **Compromise response:** see Threat Model §6.5. Roll `key_epoch`; existing tokens fail decryption; existing capabilities fail validation; force re-issuance.

---

## 6. Redemption Flow

### 6.1 Endpoint

```
POST /v1/checkin/redeem
Authentication:
  - mTLS client cert with CN matching club tenant ID, OR
  - Bearer <club_session_assertion> (PASETO v4.public, 5-minute exp)
X-Request-Id: <uuid>
Content-Type: application/json

{
  "qr_payload": "av1:v4.local....",
  "display_code": "284910",
  "session_id": "s_01HX300V8C7W3J6K9MQ5RTY",
  "redeeming_club_id": "c_01HV9R3E0M"
}
```

### 6.2 Server-side validation

1. Authenticate the redeemer (mTLS or assertion). Pull `redeeming_club_id` from the authenticated identity, **not** from the request body. The `redeeming_club_id` field in the body is asserted by the client and must equal the authenticated identity; mismatch → `403 club_assertion_mismatch`, audit event.
2. Parse the QR payload prefix, extract the PASETO bytes and the displayed code.
3. Pull `key_epoch` from the PASETO header (PASETO v4.local has a footer field we use for the epoch; we encode it as plaintext footer because the AEAD also authenticates the footer).
4. Derive the right subkey from KMS for that tenant + epoch.
5. Decrypt and verify the PASETO. Failure → `401 invalid_token`, audit event with truncated bytes.
6. Validate claims:
   - `purpose == "club_session_attribution_only"`. Otherwise 403.
   - `iat <= now + skew`, `exp >= now - skew`. Otherwise 401 `expired`.
   - `redeeming_club_id ∈ allowed_club_ids`. Otherwise 403 `club_not_allowed`, audit event (notify athlete out of band).
   - Recompute the 6-digit code from `jti || nonce || athlete_id`; require equality with `display_code`. Otherwise 401 `channel_binding_mismatch`.
7. Single-use enforcement: `SET checkin:redeemed:{jti} <redeeming_club_id> NX EX (exp - now + skew)`. Failure → 409 `already_redeemed`, audit event `checkin.second_redemption_attempt`, alert.
8. Check revocation set: `SISMEMBER checkin:revoked {jti}`. Hit → 410 `revoked`, audit event.
9. Generate the ephemeral attribution capability (see §8).
10. Emit audit event `checkin.token_redeemed` with `athlete_id`, `jti`, `redeeming_club_id`, `session_id`, `request_id`.
11. Return the capability.

### 6.3 Rate limiting

- Per-club: 30 redemptions per minute per club (a busy facility; trap > 30/min as anomaly).
- Per-athlete: at most 1 *successful* redemption per `jti` ever; failed attempts beyond 3 within 60s lock the `jti` to "burned" state and require new issuance.

---

## 7. Single-Use Enforcement

`jti` is the canonical single-use key.

- **Atomic claim:** Redis `SET checkin:redeemed:{jti} <club_id> NX EX <ttl>`. If the SET returns a non-OK (key existed), redemption fails with 409 `already_redeemed`.
- **TTL:** `(exp - now) + clock_skew_window` (5s). After the token expires, the ledger entry is harmless and is GC'd by Redis.
- **Failover:** if Redis is unavailable, the redemption endpoint returns 503 `single_use_check_unavailable`. We **do not** fall back to "allow on Redis failure"; an attacker who can DoS Redis must not be able to bypass single-use.
- **Persistence beyond TTL:** for forensic purposes, the audit log retains `jti`, redemption time, and club ID for 7 years even after the Redis entry is gone.
- **Second-redemption-attempt logging:** even though the second attempt is rejected, we log who attempted, from which IP/cert, and alert. A compromised club dashboard might attempt to "rescue" a previously-redeemed token; this is a high-fidelity tripwire.

---

## 8. Response: Ephemeral Attribution Capability

The redemption response body:

```json
{
  "attribution_capability": "v4.local.<...>",
  "session_id": "s_01HX300V8C7W3J6K9MQ5RTY",
  "expires_at": 1762374690,
  "scope": "attribution_write_only",
  "audit_chain_anchor": "sha256:..."
}
```

The capability is itself a PASETO v4.local token (separate signing key from the QR token, separate KMS key) with claims:

```json
{
  "purpose": "attribution_write_only",
  "session_id": "s_01HX300V8C7W3J6K9MQ5RTY",
  "athlete_pseudonym": "ap_01HX2ZP4N0",
  "issuing_club_id": "c_01HV9R3E0M",
  "iat": 1762371090,
  "exp": 1762374690,
  "jti": "01HX2ZP6X7Y8Z9A0B1C2D3E4F6",
  "key_epoch": 11
}
```

Critical properties:

- **`athlete_pseudonym`, not `athlete_id`.** A pseudonym scoped to this session, derived from `HMAC(session_attribution_pseudonym_key, athlete_id || session_id)`. The club never sees the underlying `athlete_id`. Cross-session linkage of pseudonyms is impossible without the HMAC key, which lives in KMS.
- **`session_id` is bound.** The capability is rejected by any endpoint other than the attribution-write endpoint for *this* session.
- **`scope = attribution_write_only`.** No history read. No annotation read. No anything else.
- **`exp` = 1 hour.** A session lasts longer than 90 seconds but shorter than a day; one hour is the standard operating window. Capability expiry forces reauth for stale sessions.

The mobile app *and* the athlete are notified that a successful redemption occurred (push notification with `redeeming_club_id` and timestamp). The athlete can dispute or revoke from the notification.

---

## 9. Attribution Endpoint

```
POST /v1/sessions/{session_id}/attributions
Authentication: Bearer <attribution_capability>     # PASETO v4.local
X-Request-Id: <uuid>
Content-Type: application/json

{
  "frame_ranges": [
    {"start_ts_ms": 12345, "end_ts_ms": 18901, "confidence": 0.94}
  ]
}
```

### 9.1 Endpoint behavior

1. Decrypt the capability with the *attribution-capability* KMS subkey (separate from the QR-token subkey).
2. Validate `purpose == "attribution_write_only"`.
3. Validate `session_id` in the URL matches the capability claim.
4. Validate `iat`/`exp`.
5. Lookup `athlete_pseudonym` → `athlete_id` via the HMAC inverse map (server-side only).
6. Append per-frame attribution markers into the session event log: `(session_id, frame_range, attributed_athlete_id, confidence, capability_jti, capability_iat)`.
7. Respond 202 with `attribution_id`.

The endpoint **only writes** to the session event log. It does not read any user history. It does not return any data beyond an attribution acknowledgement.

### 9.2 Forbidden behavior

The endpoint must explicitly reject:

- Capabilities whose `purpose` is anything other than `attribution_write_only`.
- Calls to `/users/{id}/...` paths — capability validator on those paths reports an immediate 403 `wrong_capability_type`.
- Bulk frame ranges covering more than 50% of the session (a likely indicator of a malformed or malicious attribution attempt) — soft-fail with 400 and a coach-review task.

---

## 10. Revocation

### 10.1 Athlete-initiated

The mobile app exposes "Cancel check-in" while the QR is on screen and for 60 seconds after issuance. The mobile app calls:

```
DELETE /v1/checkin/tokens/{jti}
Authorization: Bearer <athlete_session_token>
```

Server actions:

1. `SADD checkin:revoked {jti}` (with the Redis set's TTL slightly longer than the token's `exp`).
2. If the `jti` has *already* been redeemed (i.e. exists in `checkin:redeemed:{jti}`):
   - Look up the issued attribution capability's `jti`.
   - Add that capability `jti` to a revoked-capability set.
   - Future calls to the attribution endpoint with that capability fail with 410 `capability_revoked`.
3. Audit event `checkin.token_revoked` with cause = `athlete_initiated`.
4. Notify the athlete that any in-flight attribution writes will be rejected.

### 10.2 Club-initiated

A club can also revoke a capability they no longer want (e.g. they realize the wrong session was bound). Same mechanism, scoped to the capability `jti`. Audit cause = `club_initiated`.

### 10.3 System-initiated

The system revokes on:

- Detection of credential compromise on the issuing athlete account.
- Detection of compromise on the redeeming club's mTLS cert or assertion key.
- Key-epoch rotation events that explicitly invalidate prior tokens.

---

## 11. Audit Events

All events conform to `docs/security/audit-logging-spec.md` §3. Events emitted by this subsystem:

| Event                                       | Trigger                                                                                          |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `checkin.token_issued`                      | Issuance endpoint succeeds                                                                       |
| `checkin.token_issuance_rate_limited`       | Per-athlete or global rate limit hit                                                             |
| `checkin.token_redeemed`                    | Redemption succeeds                                                                              |
| `checkin.token_redemption_failed`           | Any failure in §6.2 — includes failure code (`expired`, `channel_binding_mismatch`, etc.)         |
| `checkin.second_redemption_attempt`         | NX claim fails; second redemption attempted                                                      |
| `checkin.club_allowlist_mismatch`           | `redeeming_club_id ∉ allowed_club_ids`                                                           |
| `checkin.token_revoked`                     | Revocation by athlete, club, or system                                                           |
| `checkin.capability_issued`                 | Attribution capability returned                                                                  |
| `checkin.capability_used`                   | Successful call to attribution endpoint                                                          |
| `checkin.capability_misused`                | Capability presented at non-attribution endpoint                                                 |
| `checkin.capability_revoked`                | Capability invalidated post-issuance                                                             |
| `checkin.token_expired_unredeemed`          | Janitor sees `exp < now` and `jti` never appeared in `checkin:redeemed:`                          |

Events `second_redemption_attempt`, `club_allowlist_mismatch`, and `capability_misused` are alert-grade — they fire to on-call SRE.

---

## 12. Threat Analysis

### 12.1 Token enumeration / brute force

- `jti` is 128 bits of CSPRNG output. Brute-force search infeasible.
- `display_code` is 6 digits = ~20 bits, but is gated by both possession of a valid PASETO **and** the rate-limited redemption endpoint. An attacker would need to concurrently brute-force both.
- Redemption endpoint per-`jti` failure cap at 3 within 60s prevents online brute force.

### 12.2 Replay

- Single-use ledger keyed on `jti`.
- 90-second `exp` window.
- Capability replay across sessions blocked by `session_id` binding.

### 12.3 MITM

- All traffic is TLS 1.3. Mobile app pins backend cert with backup pin; web dashboard pins cert via HSTS preload + expected-CT.
- mTLS between authenticated clubs and the redemption endpoint defeats MITM at the redemption hop.

### 12.4 Evil-twin club

- `allowed_club_ids` allowlist. A club not in the set cannot redeem regardless of network position.
- Allowlist additions are explicit consent events (audit-logged), surfaced in athlete UI, requiring confirmation.

### 12.5 Athlete impersonation

- Token cannot be issued without an authenticated athlete session.
- A stolen mobile device with a live session is the only way to issue tokens; mitigation is the device-loss path (Threat Model §4.1, §4.5).

### 12.6 Club dashboard XSS exfiltrating the capability

- Capability is short-lived (1 hour) and write-only-scoped.
- A successful XSS exfiltration would let the attacker write attributions to the *one* session whose ID is in the capability — they cannot pivot to other sessions or read history.
- The attacker writing fraudulent attributions to a session they do hold the capability for is bounded by §9.2 limits and detectable by anomaly (frames attributed without corresponding capture telemetry).
- Defense-in-depth: require Subresource Integrity for the dashboard; CSP excludes inline scripts; club dashboard sandboxed in a separate origin from the athlete dashboard.

### 12.7 Capability replay across sessions

- `session_id` binding rejects this at the attribution endpoint.
- Capability `jti` is single-use-per-call as well: capability used once locks rate-limited use to ~1Hz on that capability to prevent flood-write.

### 12.8 Backend compromise

- Out of scope of this token spec — covered in Threat Model §6.3.
- Note: a compromised backend can issue arbitrary tokens; mitigation is detection (audit chain hash break, anomaly), not prevention.

### 12.9 Coercion

- An athlete coerced to issue a token: out of scope of cryptography; safeguarding playbook addresses.

---

## 13. Implementation Pseudocode

### 13.1 Backend (Python / FastAPI)

```python
# src/checkin/tokens.py
from __future__ import annotations

import hmac
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Iterable

from pyseto import Key, Paseto
from pydantic import BaseModel, Field

from app.kms import qr_token_subkey, channel_binding_key, capability_subkey
from app.audit import emit
from app.redis_ledger import claim_jti, is_revoked, mark_revoked
from app.errors import (
    InvalidToken, Expired, ChannelBindingMismatch,
    ClubNotAllowed, AlreadyRedeemed, Revoked,
)

CLOCK_SKEW_S = 5
TOKEN_TTL_S = 90
CAPABILITY_TTL_S = 3600
PURPOSE_QR = "club_session_attribution_only"
PURPOSE_CAP = "attribution_write_only"


class IssueRequest(BaseModel):
    facility_hint: str | None = Field(default=None, max_length=64)


class IssueResponse(BaseModel):
    qr_payload: str
    display_code: str
    expires_at: int


def _channel_binding_code(jti: bytes, nonce: bytes, athlete_id: str) -> str:
    h = hmac.new(channel_binding_key(), digestmod=hashlib.blake2b)
    h.update(jti); h.update(nonce); h.update(athlete_id.encode())
    h.update(b"channel_binding_v1")
    digest_int = int.from_bytes(h.digest()[:3], "big")  # 24 bits
    return f"{digest_int % 1_000_000:06d}"


def issue(athlete_id: str, allowed_club_ids: list[str],
          facility_hint: str | None) -> IssueResponse:
    if facility_hint and facility_hint in allowed_club_ids:
        allowed_club_ids = [facility_hint]
    jti_bytes = secrets.token_bytes(16)
    nonce_bytes = secrets.token_bytes(16)
    now = int(time.time())
    claims = {
        "athlete_id": athlete_id,
        "purpose": PURPOSE_QR,
        "iat": now,
        "exp": now + TOKEN_TTL_S,
        "jti": jti_bytes.hex(),
        "nonce": nonce_bytes.hex(),
        "allowed_club_ids": allowed_club_ids,
    }
    subkey, epoch = qr_token_subkey(athlete_id)
    paseto = Paseto.new(exp=TOKEN_TTL_S, including_iat=False)
    token = paseto.encode(Key.new(version=4, purpose="local", key=subkey),
                          claims, footer=str(epoch).encode())
    code = _channel_binding_code(jti_bytes, nonce_bytes, athlete_id)
    emit("checkin.token_issued",
         actor_principal=athlete_id, target_id=jti_bytes.hex(),
         extra={"allowed_club_ids": allowed_club_ids, "exp": claims["exp"]})
    return IssueResponse(
        qr_payload=f"av1:{token.decode()}-{code}",
        display_code=code,
        expires_at=claims["exp"],
    )


@dataclass
class RedeemRequest:
    qr_payload: str
    display_code: str
    session_id: str
    redeeming_club_id: str


def redeem(req: RedeemRequest, authenticated_club_id: str) -> str:
    if req.redeeming_club_id != authenticated_club_id:
        emit("checkin.token_redemption_failed",
             actor_principal=authenticated_club_id,
             extra={"reason": "club_assertion_mismatch"})
        raise ClubNotAllowed("club_assertion_mismatch")

    if not req.qr_payload.startswith("av1:"):
        raise InvalidToken("bad_prefix")
    body = req.qr_payload[len("av1:"):]
    paseto_part, _, code_part = body.rpartition("-")
    if code_part != req.display_code:
        raise ChannelBindingMismatch()

    # epoch from footer
    epoch = int(Paseto.peek_footer(paseto_part).decode())
    subkey = qr_token_subkey_for_epoch(epoch)
    try:
        claims = Paseto.decode(Key.new(version=4, purpose="local", key=subkey),
                               paseto_part)
    except Exception:
        emit("checkin.token_redemption_failed",
             actor_principal=authenticated_club_id,
             extra={"reason": "decrypt_fail"})
        raise InvalidToken("decrypt_fail")

    now = int(time.time())
    if claims["purpose"] != PURPOSE_QR:
        raise InvalidToken("wrong_purpose")
    if claims["iat"] > now + CLOCK_SKEW_S:
        raise InvalidToken("future_iat")
    if claims["exp"] < now - CLOCK_SKEW_S:
        raise Expired()
    if authenticated_club_id not in claims["allowed_club_ids"]:
        emit("checkin.club_allowlist_mismatch",
             actor_principal=authenticated_club_id,
             target_id=claims["jti"])
        raise ClubNotAllowed("not_in_allowlist")

    jti = claims["jti"]
    nonce = bytes.fromhex(claims["nonce"])
    expected_code = _channel_binding_code(bytes.fromhex(jti), nonce,
                                          claims["athlete_id"])
    if not secrets.compare_digest(expected_code, req.display_code):
        raise ChannelBindingMismatch()

    if is_revoked(jti):
        raise Revoked()

    if not claim_jti(jti, authenticated_club_id,
                     ttl=(claims["exp"] - now) + CLOCK_SKEW_S):
        emit("checkin.second_redemption_attempt",
             actor_principal=authenticated_club_id,
             target_id=jti)
        raise AlreadyRedeemed()

    capability = _issue_capability(
        athlete_id=claims["athlete_id"],
        session_id=req.session_id,
        issuing_club_id=authenticated_club_id,
    )
    emit("checkin.token_redeemed",
         actor_principal=authenticated_club_id,
         target_id=jti,
         extra={"session_id": req.session_id})
    return capability
```

### 13.2 Mobile (TypeScript / React Native)

```ts
// mobile/src/features/checkin/issueQr.ts
import { secureFetch } from "../net/secureFetch"

export interface QrIssueResult {
  qrPayload: string
  displayCode: string
  expiresAt: number
}

export async function issueQr(facilityHint?: string): Promise<QrIssueResult> {
  const r = await secureFetch("/v1/checkin/tokens", {
    method: "POST",
    body: JSON.stringify({ facility_hint: facilityHint ?? null }),
  })
  if (!r.ok) throw new QrIssueError(await r.text())
  const j = await r.json()
  return {
    qrPayload: j.qr_payload,
    displayCode: j.display_code,
    expiresAt: j.expires_at,
  }
}

export async function cancelCheckin(jti: string): Promise<void> {
  const r = await secureFetch(`/v1/checkin/tokens/${jti}`, { method: "DELETE" })
  if (!r.ok && r.status !== 404) throw new QrIssueError(await r.text())
}
```

### 13.3 Web Dashboard (TypeScript)

```ts
// web/src/features/checkin/redeem.ts
import { clubMtlsFetch } from "../net/clubMtlsFetch"

export interface RedeemResult {
  attributionCapability: string
  sessionId: string
  expiresAt: number
}

export async function redeem(qrPayload: string, displayCode: string,
                             sessionId: string,
                             redeemingClubId: string): Promise<RedeemResult> {
  const r = await clubMtlsFetch("/v1/checkin/redeem", {
    method: "POST",
    body: JSON.stringify({
      qr_payload: qrPayload,
      display_code: displayCode,
      session_id: sessionId,
      redeeming_club_id: redeemingClubId,
    }),
  })
  if (!r.ok) throw new RedeemError(r.status, await r.text())
  const j = await r.json()
  return {
    attributionCapability: j.attribution_capability,
    sessionId: j.session_id,
    expiresAt: j.expires_at,
  }
}

export async function writeAttribution(cap: string, sessionId: string,
                                       frameRanges: FrameRange[]) {
  const r = await fetch(`/v1/sessions/${sessionId}/attributions`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${cap}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ frame_ranges: frameRanges }),
  })
  if (!r.ok) throw new AttributionError(r.status, await r.text())
  return r.json()
}
```

---

## 14. Test Cases (Minimum 20 Must-Pass)

| #  | Case                                                                                                                        | Expected outcome                                                                              |
| -- | --------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| 1  | Happy path: athlete issues QR, club in allowlist redeems within 90s with correct display_code                               | 200 + attribution capability                                                                   |
| 2  | Issuance without authenticated athlete                                                                                      | 401                                                                                            |
| 3  | Issuance for athlete with empty `allowed_club_ids`                                                                          | 422 with prompt to add at least one authorized club                                            |
| 4  | Redemption 91s after issuance                                                                                               | 401 `expired`                                                                                  |
| 5  | Redemption with wrong `display_code`                                                                                        | 401 `channel_binding_mismatch`                                                                |
| 6  | Redemption by a club not in `allowed_club_ids`                                                                              | 403 `club_not_allowed` + audit `checkin.club_allowlist_mismatch`                              |
| 7  | Second redemption of the same `jti`                                                                                         | 409 `already_redeemed` + audit `checkin.second_redemption_attempt` + alert                     |
| 8  | Redemption with PASETO whose `purpose` was tampered                                                                         | 401 `decrypt_fail` (AEAD failure)                                                              |
| 9  | Redemption when Redis is down                                                                                               | 503 `single_use_check_unavailable` (no fallback to allow)                                      |
| 10 | Redemption with `redeeming_club_id` body claim mismatching mTLS-authenticated identity                                       | 403 `club_assertion_mismatch`                                                                  |
| 11 | Athlete revokes after issuance, before redemption                                                                           | 410 `revoked` on redemption attempt                                                            |
| 12 | Athlete revokes *after* redemption                                                                                          | Capability becomes invalid; subsequent attribution-endpoint call returns 410 `capability_revoked` |
| 13 | Capability used at `/users/{id}/sessions`                                                                                    | 403 `wrong_capability_type` + audit `checkin.capability_misused`                              |
| 14 | Capability used at attribution endpoint with a different `session_id`                                                        | 403 `session_id_mismatch`                                                                     |
| 15 | Capability used 1h+ after issuance                                                                                          | 401 `expired`                                                                                  |
| 16 | Issuance rate limit (>5/min per athlete)                                                                                    | 429 + audit `checkin.token_issuance_rate_limited`                                              |
| 17 | Redemption rate limit (>30/min per club)                                                                                    | 429                                                                                            |
| 18 | Token issued under `key_epoch=N`, then root key rotates to `N+1`, redeemed within 24h grace                                  | 200                                                                                            |
| 19 | Token issued under `key_epoch=N`, redeemed after 24h post-rotation                                                           | 401 `decrypt_fail` (subkey zeroized)                                                          |
| 20 | Capability used to write attribution for >50% of session frames                                                             | 400 + coach-review task surfaced                                                                |
| 21 | QR payload with unknown prefix `av2:`                                                                                       | 400 `unsupported_version`                                                                     |
| 22 | Redemption with malformed PASETO bytes                                                                                       | 401 `invalid_token`                                                                           |
| 23 | Capability claims edited (replay with substituted `session_id`)                                                              | AEAD failure → 401                                                                            |
| 24 | `facility_hint` provided that is not in the athlete's allowlist                                                              | Token issued with full allowlist (hint silently ignored), or 400 — implementation decision. Default: 400 with prompt to authorize. |
| 25 | Two simultaneous redemptions of the same `jti` from two clubs — race                                                         | Exactly one wins (Redis NX); the other gets 409 + audit                                        |

These tests must be in the CI suite for any change touching the check-in subsystem. Coverage tool must verify the redemption code path is exercised end-to-end.

---

## 15. Open Questions

1. **`allowed_club_ids` onboarding UX.** How does an athlete pre-authorize a club they have never visited?
   - **Option A:** Coach at the club generates an "invite QR" containing the club's signed `club_id`; athlete scans in their mobile app, which verifies the signature against a known-clubs registry and adds to the allowlist. Pros: no typing; verifiable. Cons: requires coach contact before first visit.
   - **Option B:** Club's signup landing page deep-links into the mobile app with a signed `club_id` payload. Pros: marketing-friendly. Cons: deep-link spoofing risk; mitigated by signature.
   - **Option C:** Athlete enters a 6-character club code during onboarding; backend verifies and adds. Pros: simple. Cons: code phishing.
   - **Recommendation:** Option A as primary, Option B as fallback. Option C only as a manual-entry escape hatch behind an extra confirmation.

2. **Should `allowed_club_ids` expire?** A club the athlete visited once 5 years ago should probably not still be authorized. Recommendation: each authorization has an `expires_at` defaulting to 12 months, with renew-on-visit behavior.

3. **Does the federation tier need a parallel design?** Federation-managed sessions are outside this spec — federations operate their own attribution flows for their cohorts. If a Solo user visits a federation-tier session, do they need a check-in? Recommendation: yes, same flow, with `redeeming_org_type = federation`. Defer detailed design to Sprint 18.

4. **Channel-binding code length.** 6 digits = 20 bits is sufficient given the 90-second window and rate limits, but if facilities prefer voice-readable, consider 4 words from the EFF wordlist (~52 bits, much higher entropy). Decision pending UX research.

5. **Can the same `jti` be revoked *and* redeemed?** No — revocation set is consulted before NX claim. Revocation must beat redemption to effect. UX: show a brief confirmation modal on cancel that explains the race window.

6. **Auto-bind QR (display_code embedded).** A facility setting; default off. Decide whether this is enabled for federation-tier sessions where high trust + speed matter. Decision pending federation feedback.

---

End of QR check-in token spec v1.0.

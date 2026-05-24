"""GoTrue (Supabase Auth) JWT verifier.

Per ADR-0010, Phase-1 identity is GoTrue (self-hosted) but the AIMVISION
backend keeps tenancy, memberships, and RLS. The login endpoint will
accept a GoTrue-issued JWT, validate it here, and then mint an
AIMVISION-side session token via ``services.auth.issue_token`` that
carries the resolved ``(user_id, tenant_id, role)`` tuple.

This module owns *only* the GoTrue-token validation step. It does not
issue tokens, does not touch the membership tables, and does not run in
the request hot path until ``Settings.auth_provider == "gotrue"`` AND the
``/auth/login`` integration follow-up lands.

Verification supports two key strategies:

* **HS256** — symmetric secret shared with the GoTrue process. The
  most common self-hosted GoTrue / Supabase Auth dev configuration; the
  same `GOTRUE_JWT_SECRET` env that GoTrue itself uses.
* **RS256** — asymmetric, with a pinned PEM-encoded public key
  (``gotrue_jwt_public_key_pem``). Set this when GoTrue runs with
  ``GOTRUE_JWT_KEY_TYPE=rsa``. JWKS-endpoint rotation is a follow-up
  (tracked in ADR-0010's "Migration" section).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from jwt.types import Options as JWTDecodeOptions

from ..config import Settings, get_settings

# GoTrue's default audience for end-user-issued tokens. Tokens minted for
# the service role use ``aud = "service_role"`` and must never reach an
# end-user-bound endpoint; we reject anything that isn't explicitly the
# configured audience.
DEFAULT_GOTRUE_AUDIENCE = "authenticated"


class GoTrueVerificationError(Exception):
    """Raised when a GoTrue JWT fails validation for any reason.

    The router maps this to HTTP 401; the message is *not* surfaced to the
    client (it could leak which check failed). Audit-log the exception
    cause separately if you need attack-surface telemetry.
    """


@dataclass(frozen=True)
class GoTrueClaims:
    """The subset of GoTrue claims AIMVISION actually consumes.

    Kept narrow on purpose: the AIMVISION backend resolves role + tenant
    from its own ``memberships`` table, so role-like claims on the GoTrue
    side (``role`` = ``"authenticated"``/``"service_role"``) are
    deliberately not propagated as authorization signal. ``aud`` is
    *checked* against the configured audience but not returned.
    """

    sub: str
    email: str | None
    email_verified: bool
    session_id: str | None
    issued_at: int
    expires_at: int
    raw: dict[str, Any]


def _resolve_decode_kwargs(s: Settings) -> tuple[str, str | bytes, JWTDecodeOptions]:
    """Pick algorithm + key + decode-options from settings.

    Raises ``GoTrueVerificationError`` if the configuration is incomplete
    for the requested algorithm. This is a startup-time misconfiguration
    surfaced as an auth failure at the first request — loud and fast.
    """
    alg = (s.gotrue_jwt_alg or "HS256").upper()
    if alg == "HS256":
        if not s.gotrue_jwt_secret:
            raise GoTrueVerificationError("gotrue_jwt_secret is not configured")
        key: str | bytes = s.gotrue_jwt_secret
    elif alg in {"RS256", "RS384", "RS512", "ES256", "ES384"}:
        if not s.gotrue_jwt_public_key_pem:
            raise GoTrueVerificationError(f"gotrue_jwt_public_key_pem is not configured for {alg}")
        key = s.gotrue_jwt_public_key_pem.encode("utf-8")
    else:
        raise GoTrueVerificationError(f"unsupported gotrue_jwt_alg: {alg}")

    options: JWTDecodeOptions = {
        "require": ["exp", "iat", "sub", "aud", "iss"],
        "verify_signature": True,
        "verify_exp": True,
        "verify_iat": True,
        "verify_aud": True,
        "verify_iss": True,
    }
    return alg, key, options


def verify_gotrue_jwt(token: str, *, settings: Settings | None = None) -> GoTrueClaims:
    """Validate a GoTrue-issued JWT and return its claims.

    Always raises :class:`GoTrueVerificationError` on any failure mode
    (bad signature, expired, wrong issuer/audience, missing required
    claim, malformed token). The caller maps that to a generic 401 with
    no detail leakage.
    """
    s = settings or get_settings()
    if not s.gotrue_issuer:
        raise GoTrueVerificationError("gotrue_issuer is not configured")
    audience = s.gotrue_audience or DEFAULT_GOTRUE_AUDIENCE

    alg, key, options = _resolve_decode_kwargs(s)
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[alg],
            audience=audience,
            issuer=s.gotrue_issuer,
            options=options,
        )
    except jwt.PyJWTError as exc:
        raise GoTrueVerificationError(f"invalid gotrue jwt: {exc.__class__.__name__}") from exc

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise GoTrueVerificationError("gotrue jwt missing sub")

    email_raw = payload.get("email")
    email = email_raw if isinstance(email_raw, str) and email_raw else None
    # GoTrue surfaces verification state inside `user_metadata` or as a
    # top-level `email_verified` boolean depending on version; accept
    # either, default False.
    if isinstance(payload.get("email_verified"), bool):
        email_verified = bool(payload["email_verified"])
    else:
        md = payload.get("user_metadata") or {}
        email_verified = bool(md.get("email_verified", False))

    sid_raw = payload.get("session_id")
    session_id = sid_raw if isinstance(sid_raw, str) and sid_raw else None

    iat = payload.get("iat")
    exp = payload.get("exp")
    if not isinstance(iat, int) or not isinstance(exp, int):
        raise GoTrueVerificationError("gotrue jwt iat/exp must be ints")

    return GoTrueClaims(
        sub=sub,
        email=email,
        email_verified=email_verified,
        session_id=session_id,
        issued_at=iat,
        expires_at=exp,
        raw=payload,
    )

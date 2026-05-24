"""GoTrue JWT verifier — happy + every documented failure mode.

The verifier is the gate that lets a Supabase-Auth-issued token translate
to an AIMVISION principal (ADR-0010). Every rejection here is a real
attack surface we don't want to silently swallow.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import jwt
import pytest

from app.config import Settings
from app.services.auth_gotrue import (
    DEFAULT_GOTRUE_AUDIENCE,
    GoTrueVerificationError,
    verify_gotrue_jwt,
)

HS_SECRET = "test-gotrue-shared-secret-please-32-bytes-long-x"
ISSUER = "https://gotrue.test.local"
USER_ID = "00000000-0000-0000-0000-0000000000aa"


def _hs_settings(**overrides: object) -> Settings:
    """Settings tuned to exercise the HS256 GoTrue path. Each call returns
    a fresh instance so test mutations don't leak across cases."""
    base: dict[str, object] = {
        "auth_provider": "gotrue",
        "gotrue_jwt_alg": "HS256",
        "gotrue_jwt_secret": HS_SECRET,
        "gotrue_issuer": ISSUER,
        "gotrue_audience": DEFAULT_GOTRUE_AUDIENCE,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _mint(
    *,
    secret: str = HS_SECRET,
    alg: str = "HS256",
    sub: str = USER_ID,
    iss: str = ISSUER,
    aud: str = DEFAULT_GOTRUE_AUDIENCE,
    iat_offset: int = 0,
    exp_offset: int = 3600,
    email: str | None = "athlete@example.com",
    email_verified: bool | None = True,
    extra: dict[str, object] | None = None,
    drop: Iterator[str] = (),
) -> str:
    """Mint a GoTrue-shaped JWT. ``drop`` lets a test strip a required
    claim to prove the verifier rejects malformed tokens."""
    now = int(time.time())
    payload: dict[str, object] = {
        "sub": sub,
        "aud": aud,
        "iss": iss,
        "iat": now + iat_offset,
        "exp": now + exp_offset,
    }
    if email is not None:
        payload["email"] = email
    if email_verified is not None:
        payload["email_verified"] = email_verified
    if extra:
        payload.update(extra)
    for key in drop:
        payload.pop(key, None)
    return jwt.encode(payload, secret, algorithm=alg)


def test_valid_hs256_token_returns_claims() -> None:
    token = _mint(extra={"session_id": "sess-xyz"})
    claims = verify_gotrue_jwt(token, settings=_hs_settings())
    assert claims.sub == USER_ID
    assert claims.email == "athlete@example.com"
    assert claims.email_verified is True
    assert claims.session_id == "sess-xyz"
    assert claims.expires_at > claims.issued_at


def test_email_verified_falls_back_to_user_metadata() -> None:
    token = _mint(
        email_verified=None,
        extra={"user_metadata": {"email_verified": True}},
    )
    claims = verify_gotrue_jwt(token, settings=_hs_settings())
    assert claims.email_verified is True


def test_email_verified_defaults_false_when_absent() -> None:
    token = _mint(email_verified=None)
    claims = verify_gotrue_jwt(token, settings=_hs_settings())
    assert claims.email_verified is False


def test_bad_signature_rejected() -> None:
    token = _mint(secret="a-totally-different-secret-also-32-bytes-x")
    with pytest.raises(GoTrueVerificationError):
        verify_gotrue_jwt(token, settings=_hs_settings())


def test_wrong_issuer_rejected() -> None:
    token = _mint(iss="https://someone-elses-gotrue.example")
    with pytest.raises(GoTrueVerificationError):
        verify_gotrue_jwt(token, settings=_hs_settings())


def test_wrong_audience_rejected() -> None:
    # The service-role token must never be accepted on an end-user path.
    token = _mint(aud="service_role")
    with pytest.raises(GoTrueVerificationError):
        verify_gotrue_jwt(token, settings=_hs_settings())


def test_expired_token_rejected() -> None:
    token = _mint(iat_offset=-7200, exp_offset=-3600)
    with pytest.raises(GoTrueVerificationError):
        verify_gotrue_jwt(token, settings=_hs_settings())


@pytest.mark.parametrize("missing", ["sub", "iss", "aud", "exp", "iat"])
def test_missing_required_claim_rejected(missing: str) -> None:
    token = _mint(drop=(missing,))
    with pytest.raises(GoTrueVerificationError):
        verify_gotrue_jwt(token, settings=_hs_settings())


def test_empty_sub_rejected() -> None:
    token = _mint(sub="")
    with pytest.raises(GoTrueVerificationError):
        verify_gotrue_jwt(token, settings=_hs_settings())


def test_garbage_token_rejected() -> None:
    with pytest.raises(GoTrueVerificationError):
        verify_gotrue_jwt("not-a-jwt-at-all", settings=_hs_settings())


def test_missing_gotrue_secret_is_a_misconfig() -> None:
    token = _mint()
    settings = _hs_settings(gotrue_jwt_secret=None)
    with pytest.raises(GoTrueVerificationError, match="gotrue_jwt_secret"):
        verify_gotrue_jwt(token, settings=settings)


def test_missing_gotrue_issuer_is_a_misconfig() -> None:
    token = _mint()
    settings = _hs_settings(gotrue_issuer=None)
    with pytest.raises(GoTrueVerificationError, match="gotrue_issuer"):
        verify_gotrue_jwt(token, settings=settings)


def test_unsupported_alg_rejected() -> None:
    settings = _hs_settings(gotrue_jwt_alg="HS512")  # not on the allowlist
    token = _mint(alg="HS512")
    with pytest.raises(GoTrueVerificationError, match="unsupported"):
        verify_gotrue_jwt(token, settings=settings)


def test_alg_mismatch_with_key_class_rejected() -> None:
    """If settings say HS256 but the token claims to be RS256 (or any other
    family), pyjwt's algorithm-locked decode path must reject it."""
    rs_token = jwt.encode(
        {
            "sub": USER_ID,
            "aud": DEFAULT_GOTRUE_AUDIENCE,
            "iss": ISSUER,
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
        },
        HS_SECRET,
        algorithm="HS384",  # not the configured alg
    )
    with pytest.raises(GoTrueVerificationError):
        verify_gotrue_jwt(rs_token, settings=_hs_settings())


def test_rs256_requires_public_key() -> None:
    settings = _hs_settings(
        gotrue_jwt_alg="RS256",
        gotrue_jwt_public_key_pem=None,
    )
    with pytest.raises(GoTrueVerificationError, match="gotrue_jwt_public_key_pem"):
        verify_gotrue_jwt("ignored", settings=settings)

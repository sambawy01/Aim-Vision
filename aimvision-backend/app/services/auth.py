"""JWT issuance and verification.

Stub for the production PASETO/OIDC path (see ADR-0008). Sufficient as a
test-token issuer for Sprint 1.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any

import jwt

from ..config import Settings, get_settings


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    role: str


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """PBKDF2-HMAC-SHA256 password hash. bcrypt/argon2id is the production target;
    this is a stable, stdlib-only stand-in usable in tests and bootstrap envs."""
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"pbkdf2_sha256$200000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    salt = bytes.fromhex(salt_hex)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
    return hmac.compare_digest(candidate.hex(), digest_hex)


def issue_token(
    principal: Principal,
    *,
    settings: Settings | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[str, int]:
    s = settings or get_settings()
    now = int(time.time())
    exp = now + s.jwt_ttl_seconds
    payload: dict[str, Any] = {
        "sub": principal.user_id,
        "tid": principal.tenant_id,
        "role": principal.role,
        "iat": now,
        "exp": exp,
        "iss": "aimvision",
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_alg)
    return token, s.jwt_ttl_seconds


def verify_token(token: str, *, settings: Settings | None = None) -> Principal:
    s = settings or get_settings()
    payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_alg], issuer="aimvision")
    return Principal(
        user_id=str(payload["sub"]),
        tenant_id=str(payload["tid"]),
        role=str(payload["role"]),
    )

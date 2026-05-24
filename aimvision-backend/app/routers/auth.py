"""Auth endpoints: signup + login (issues a stub JWT)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..deps import db_session_anon
from ..models.tenancy import Account, Membership, OrgKind, Role, User
from ..models.tenancy import Org as OrgModel
from ..schemas.tenancy import (
    GoTrueExchangeIn,
    LoginIn,
    LoginOut,
    MembershipOut,
    PrincipalOut,
    SignupIn,
    UserOut,
)
from ..services.auth import Principal, hash_password, issue_token, verify_password
from ..services.auth_gotrue import GoTrueVerificationError, verify_gotrue_jwt
from ..services.authz import ROLE_RANK

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupIn,
    session: AsyncSession = Depends(db_session_anon),
) -> UserOut:
    existing = await session.execute(select(User).where(User.email == payload.email))
    if existing.scalars().first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="email already registered")

    account = Account(name=payload.display_name)
    session.add(account)
    await session.flush()

    user = User(
        account_id=account.id,
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
    )
    session.add(user)
    await session.flush()

    solo_tenant = f"solo:{user.id}"
    solo_org = OrgModel(
        kind=OrgKind.solo,
        name=f"{payload.display_name} (solo)",
        tenant_id=solo_tenant,
    )
    session.add(solo_org)
    await session.flush()

    return UserOut(id=user.id, email=user.email, display_name=user.display_name)


@router.post("/login", response_model=LoginOut)
async def login(
    payload: LoginIn,
    session: AsyncSession = Depends(db_session_anon),
) -> LoginOut:
    result = await session.execute(select(User).where(User.email == payload.email))
    user: User | None = result.scalars().first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    memberships = await _resolve_memberships(session, user)
    # The token is minted for the user's highest-privilege membership; that
    # membership is returned first so the web's `current` tenant matches the
    # token's `tid`.
    primary = memberships[0]
    principal = Principal(user_id=user.id, tenant_id=primary.tenant_id, role=primary.role)
    token, ttl = issue_token(principal)
    return LoginOut(
        access_token=token,
        expires_in=ttl,
        principal=PrincipalOut(
            user_id=user.id,
            tenant_id=primary.tenant_id,
            role=primary.role,
            display_name=user.display_name,
        ),
        memberships=memberships,
    )


@router.post("/exchange", response_model=LoginOut)
async def exchange_gotrue_token(
    payload: GoTrueExchangeIn,
    session: AsyncSession = Depends(db_session_anon),
) -> LoginOut:
    """Exchange a GoTrue-issued JWT for an AIMVISION session (ADR-0010).

    The client authenticates against GoTrue directly (signup, password,
    MFA all live there) and posts the resulting JWT here. We verify it,
    look up the AIMVISION ``users`` row mirrored by ``gotrue_sub``, and
    mint our own session token bound to that user's highest-privilege
    membership. The response shape matches ``/auth/login`` so the web
    + mobile clients can swap the entry point without further changes.

    First-login provisioning (creating an AIMVISION ``users`` row from
    GoTrue claims the first time a user appears) is deliberately *not*
    in this slice — it lands with the bulk-import migration script
    described in ADR-0010's Migration section. Until then, a token for
    an unknown ``sub`` is a 401, not an auto-account-create.

    Returns 401 on any failure path (invalid token, unknown sub, inactive
    user, no memberships). Failure reasons are not surfaced to the
    client; the verifier's audit-log captures them server-side.
    """
    settings = get_settings()
    if settings.auth_provider != "gotrue":
        # The endpoint exists in code but is operationally disabled until
        # the operator flips AUTH_PROVIDER. Returning 404 (not 403) keeps
        # the stub-auth deployment from advertising a GoTrue surface.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not found")

    try:
        claims = verify_gotrue_jwt(payload.gotrue_jwt, settings=settings)
    except GoTrueVerificationError as exc:
        # Single 401 for every failure mode; the verifier exception type
        # is intentionally opaque to the client. Server logs (audit) carry
        # the cause for ops + intrusion-detection.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="invalid identity token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = (
        (await session.execute(select(User).where(User.gotrue_sub == claims.sub))).scalars().first()
    )
    if user is None or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="invalid identity token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    memberships = await _resolve_memberships(session, user)
    primary = memberships[0]
    principal = Principal(user_id=user.id, tenant_id=primary.tenant_id, role=primary.role)
    token, ttl = issue_token(principal)
    return LoginOut(
        access_token=token,
        expires_in=ttl,
        principal=PrincipalOut(
            user_id=user.id,
            tenant_id=primary.tenant_id,
            role=primary.role,
            display_name=user.display_name,
        ),
        memberships=memberships,
    )


async def _resolve_memberships(session: AsyncSession, user: User) -> list[MembershipOut]:
    """Build the tenancies a user can operate in, highest-privilege first.

    Every user has an implicit solo tenancy (the solo Org created at signup);
    real `Membership` rows in clubs/federations are layered on top. When a user
    holds several roles in one tenant, the highest-ranked wins for that tenant.
    """
    solo_tenant = f"solo:{user.id}"
    solo_org = (
        (await session.execute(select(OrgModel).where(OrgModel.tenant_id == solo_tenant)))
        .scalars()
        .first()
    )
    solo_name = solo_org.name if solo_org is not None else f"{user.display_name} (solo)"

    # tenant_id -> (display_name, best_role)
    by_tenant: dict[str, tuple[str, str]] = {solo_tenant: (solo_name, Role.athlete.value)}

    rows = (
        await session.execute(
            select(Membership, OrgModel)
            .join(OrgModel, Membership.org_id == OrgModel.id)
            .where(Membership.user_id == user.id, Membership.is_active.is_(True))
        )
    ).all()
    for membership, org in rows:
        role = membership.role.value if hasattr(membership.role, "value") else str(membership.role)
        existing = by_tenant.get(org.tenant_id)
        if existing is None or ROLE_RANK.get(role, -1) > ROLE_RANK.get(existing[1], -1):
            by_tenant[org.tenant_id] = (org.name, role)

    out = [
        MembershipOut(tenant_id=tid, display_name=name, role=role)
        for tid, (name, role) in by_tenant.items()
    ]
    # Highest-privilege first; stable name order within equal rank.
    out.sort(key=lambda m: (-ROLE_RANK.get(m.role, -1), m.display_name))
    return out

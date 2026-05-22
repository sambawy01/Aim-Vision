"""Auth endpoints: signup + login + refresh + logout (issues a stub JWT)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..deps import current_principal, db_session_anon
from ..models.tenancy import Account, Membership, OrgKind, Role, User
from ..models.tenancy import Org as OrgModel
from ..schemas.tenancy import (
    LoginIn,
    LoginOut,
    MembershipOut,
    PrincipalOut,
    RefreshOut,
    SignupIn,
    SwitchTenantIn,
    SwitchTenantOut,
    UserOut,
)
from ..services.auth import (
    Principal,
    hash_password,
    issue_refresh_token,
    issue_token,
    verify_password,
    verify_refresh_token,
)
from ..services.authz import ROLE_RANK

router = APIRouter(prefix="/auth", tags=["auth"])

# httpOnly cookie carrying the refresh token. SameSite=Lax is fine for the
# same-site dev setup (localhost:5173 → localhost:8000) and for a same-site
# prod deploy; Secure is enabled outside development.
REFRESH_COOKIE = "av_refresh"


def _set_refresh_cookie(response: Response, principal: Principal) -> None:
    token, ttl = issue_refresh_token(principal)
    # Secure only in HTTPS-served environments. `development` (Vite over http)
    # and `test` (httpx over http) must stay non-secure or the cookie is never
    # sent back.
    secure = get_settings().env not in {"development", "test"}
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=ttl,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


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
    response: Response,
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
    _set_refresh_cookie(response, principal)
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


@router.post("/refresh", response_model=RefreshOut)
async def refresh(request: Request, response: Response) -> RefreshOut:
    """Exchange the httpOnly refresh cookie for a fresh access token.

    The web calls this on a 401 and retries the original request, so an
    expired access token is renewed silently instead of logging the user out.
    Stateless: the new access token is minted from the refresh token's claims.
    """
    cookie = request.cookies.get(REFRESH_COOKIE)
    if not cookie:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing refresh token")
    try:
        principal = verify_refresh_token(cookie)
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token") from exc
    token, ttl = issue_token(principal)
    # Slide the refresh window so an active session doesn't expire mid-use.
    _set_refresh_cookie(response, principal)
    return RefreshOut(access_token=token, expires_in=ttl)


@router.post("/switch-tenant", response_model=SwitchTenantOut)
async def switch_tenant(
    payload: SwitchTenantIn,
    response: Response,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(db_session_anon),
) -> SwitchTenantOut:
    """Re-mint the access token bound to a different tenancy.

    The token's `tid` claim binds the session to one tenant; switching tenants
    in the UI therefore requires a fresh token (the middleware rejects an
    `X-Tenant-Scope` that disagrees with `tid`). Callers must hold a valid
    token for their *current* tenant and may only switch to a tenant they're
    actually a member of (403 otherwise).
    """
    user = await session.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="unknown user")

    memberships = await _resolve_memberships(session, user)
    target = next((m for m in memberships if m.tenant_id == payload.tenant_id), None)
    if target is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="not a member of the requested tenant"
        )

    new_principal = Principal(user_id=user.id, tenant_id=target.tenant_id, role=target.role)
    token, ttl = issue_token(new_principal)
    # Rotate the refresh cookie too, so a later silent refresh keeps the user
    # in the tenant they switched to rather than snapping back.
    _set_refresh_cookie(response, new_principal)
    return SwitchTenantOut(
        access_token=token,
        expires_in=ttl,
        principal=PrincipalOut(
            user_id=user.id,
            tenant_id=target.tenant_id,
            role=target.role,
            display_name=user.display_name,
        ),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    """Clear the refresh cookie. The access token is bearer-held client-side
    and simply discarded by the caller."""
    response.delete_cookie(REFRESH_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


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

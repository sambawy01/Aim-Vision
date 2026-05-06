"""Auth endpoints: signup + login (issues a stub JWT)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import db_session_anon
from ..models.tenancy import Account, OrgKind, User
from ..models.tenancy import Org as OrgModel
from ..schemas.tenancy import LoginIn, LoginOut, SignupIn, UserOut
from ..services.auth import Principal, hash_password, issue_token, verify_password

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

    principal = Principal(user_id=user.id, tenant_id=f"solo:{user.id}", role="athlete")
    token, ttl = issue_token(principal)
    return LoginOut(access_token=token, expires_in=ttl)

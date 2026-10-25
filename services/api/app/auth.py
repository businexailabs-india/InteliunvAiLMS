import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session, set_request_context
from app.models import InstitutionMembership, Role, User, UserRoleAssignment


@dataclass(frozen=True)
class Principal:
    subject: str
    institution_id: UUID


@dataclass(frozen=True)
class TenantContext:
    user_id: UUID
    institution_id: UUID
    role_codes: tuple[str, ...] = field(default_factory=tuple)
    display_name: str = ""
    email: str | None = None


class OIDCVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.jwks = PyJWKClient(str(settings.oidc_jwks_url), cache_keys=True)

    def _decode(self, token: str) -> dict:
        signing_key = self.jwks.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=self.settings.oidc_audience,
            issuer=str(self.settings.oidc_issuer),
            options={"require": ["exp", "iat", "sub", "institution_id"]},
        )

    async def verify(self, token: str) -> Principal:
        try:
            claims = await asyncio.to_thread(self._decode, token)
            return Principal(
                subject=claims["sub"],
                institution_id=UUID(claims["institution_id"]),
            )
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or incomplete access token",
            ) from exc


def decode_demo_token(token: str, settings: Settings) -> Principal:
    try:
        claims = jwt.decode(
            token,
            settings.demo_jwt_secret,
            algorithms=["HS256"],
            audience=settings.oidc_audience,
            issuer="businex-demo",
            options={"require": ["exp", "iat", "sub", "institution_id"]},
        )
        return Principal(subject=claims["sub"], institution_id=UUID(claims["institution_id"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or incomplete access token",
        ) from exc


def issue_demo_token(*, subject: str, institution_id: UUID, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": subject,
            "institution_id": str(institution_id),
            "iat": now,
            "exp": now + timedelta(hours=12),
            "aud": settings.oidc_audience,
            "iss": "businex-demo",
        },
        settings.demo_jwt_secret,
        algorithm="HS256",
    )


def get_verifier(settings: Settings = Depends(get_settings)) -> OIDCVerifier:
    return OIDCVerifier(settings)


async def get_principal(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    verifier: OIDCVerifier = Depends(get_verifier),
) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    if settings.auth_mode == "demo":
        return decode_demo_token(token, settings)
    return await verifier.verify(token)


async def get_tenant_context(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> TenantContext:
    user = await session.scalar(select(User).where(User.external_subject == principal.subject))
    if user is None and "@" in principal.subject:
        user = await session.scalar(select(User).where(User.email == principal.subject))
    if user is None or not user.active:
        raise HTTPException(status_code=403, detail="Active user membership required")

    await set_request_context(
        session,
        user_id=user.id,
        institution_id=principal.institution_id,
    )
    membership = await session.scalar(
        select(InstitutionMembership).where(
            InstitutionMembership.institution_id == principal.institution_id,
            InstitutionMembership.user_id == user.id,
            InstitutionMembership.status == "active",
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Institution membership required")
    role_codes = list(
        await session.scalars(
            select(Role.code)
            .join(UserRoleAssignment, UserRoleAssignment.role_id == Role.id)
            .where(
                UserRoleAssignment.institution_id == principal.institution_id,
                UserRoleAssignment.user_id == user.id,
            )
        )
    )
    return TenantContext(
        user_id=user.id,
        institution_id=principal.institution_id,
        role_codes=tuple(role_codes),
        display_name=user.display_name,
        email=user.email,
    )

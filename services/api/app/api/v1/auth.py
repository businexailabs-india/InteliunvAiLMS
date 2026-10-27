import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TenantContext, get_tenant_context, issue_demo_token
from app.config import get_settings
from app.db import get_session, set_request_context
from app.models import Institution, InstitutionMembership, Role, User, UserRoleAssignment
from app.passwords import hash_password, verify_password
from app.schemas import DemoLoginRequest, RegisterRequest, SessionResponse
from app.security.permissions import effective_permissions

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

ROLE_CODES = {
    "Student": "student",
    "Teacher / Faculty": "teacher",
    "Training Coordinator": "coordinator",
    "Parent / Guardian / HOD": "parent_guardian",
    "Principal / L&D Lead": "principal_academic_director",
    "Administrator": "institution_admin",
    "student": "student",
    "teacher": "teacher",
    "coordinator": "coordinator",
    "parent_guardian": "parent_guardian",
    "principal_academic_director": "principal_academic_director",
    "institution_admin": "institution_admin",
}

INSTITUTION_ALIASES = {
    "northstar international school": "demo-tenant-1",
    "meridian college of technology": "demo-tenant-2",
    "horizon global university": "demo-tenant-3",
}

ROLE_NAMES = {
    "institution_admin": "Institution Admin",
    "principal_academic_director": "Principal / Academic Director",
    "coordinator": "Academic Coordinator",
    "teacher": "Teacher / Faculty",
    "student": "Student",
    "parent_guardian": "Parent / Guardian",
}


@router.post("/demo-login", response_model=SessionResponse)
async def demo_login(
    payload: DemoLoginRequest,
    session: AsyncSession = Depends(get_session),
) -> SessionResponse:
    settings = get_settings()
    if settings.auth_mode != "demo":
        raise HTTPException(status_code=403, detail="Demo login is disabled")

    user = await session.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="Unknown or inactive account")
    if user.password_hash:
        if not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
    elif payload.password != settings.demo_password:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    candidates = list(await session.scalars(select(Institution).where(Institution.status == "active")))
    if payload.institution_slug:
        candidates = [row for row in candidates if row.slug == payload.institution_slug]
        if not candidates:
            raise HTTPException(status_code=404, detail="Institution not found")

    institution: Institution | None = None
    for candidate in candidates:
        await set_request_context(session, user_id=user.id, institution_id=candidate.id)
        membership = await session.scalar(
            select(InstitutionMembership).where(
                InstitutionMembership.institution_id == candidate.id,
                InstitutionMembership.user_id == user.id,
                InstitutionMembership.status == "active",
            )
        )
        if membership is not None:
            institution = candidate
            break
    if institution is None:
        raise HTTPException(status_code=403, detail="No active institution membership")

    await set_request_context(session, user_id=user.id, institution_id=institution.id)
    roles = list(
        await session.scalars(
            select(Role.code)
            .join(UserRoleAssignment, UserRoleAssignment.role_id == Role.id)
            .where(
                UserRoleAssignment.user_id == user.id,
                UserRoleAssignment.institution_id == institution.id,
            )
        )
    )
    token = issue_demo_token(
        subject=user.external_subject,
        institution_id=institution.id,
        settings=settings,
    )
    return SessionResponse(
        access_token=token,
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        institution_id=institution.id,
        institution_name=institution.name,
        institution_slug=institution.slug,
        roles=roles,
        permissions=sorted(effective_permissions(roles)),
        auth_mode="demo",
        synthetic=True,
    )


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:70]
    return slug or "institution"


async def _institution_for(session: AsyncSession, name: str, *, create: bool) -> Institution:
    cleaned = name.strip()
    alias = INSTITUTION_ALIASES.get(cleaned.lower())
    if alias and not create:
        found = await session.scalar(select(Institution).where(Institution.slug == alias))
        if found is not None:
            return found
    found = await session.scalar(select(Institution).where(func.lower(Institution.name) == cleaned.lower()))
    if found is not None:
        return found
    if not create and alias is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    slug = _slugify(cleaned)
    if await session.scalar(select(Institution).where(Institution.slug == slug)):
        slug = f"{slug[:60]}-{uuid.uuid4().hex[:6]}"
    institution = Institution(
        id=uuid.uuid4(),
        slug=slug,
        name=cleaned,
        status="active",
        tenant_type="education",
        branding={},
        synthetic=True,
    )
    session.add(institution)
    await session.flush()
    for code, role_name in ROLE_NAMES.items():
        session.add(Role(id=uuid.uuid4(), institution_id=institution.id, code=code, name=role_name))
    await session.flush()
    return institution


@router.post("/register", response_model=SessionResponse)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> SessionResponse:
    settings = get_settings()
    if settings.auth_mode != "demo":
        raise HTTPException(status_code=403, detail="Registration is disabled")
    if not re.search(r"\d", payload.password) or not re.search(r"[A-Z]", payload.password):
        raise HTTPException(
            status_code=422,
            detail="Password needs at least 8 characters, one number, and one uppercase letter",
        )
    email = payload.email.lower().strip()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    role_code = ROLE_CODES.get(payload.role)
    if role_code is None:
        raise HTTPException(status_code=422, detail="Choose a supported account type")
    if await session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    institution = await _institution_for(session, payload.institution_name, create=payload.create_institution)
    role = await session.scalar(
        select(Role).where(Role.institution_id == institution.id, Role.code == role_code)
    )
    if role is None:
        role = Role(id=uuid.uuid4(), institution_id=institution.id, code=role_code, name=ROLE_NAMES.get(role_code, role_code))
        session.add(role)
        await session.flush()

    user = User(
        id=uuid.uuid4(),
        external_subject=email,
        display_name=f"{payload.first_name.strip()} {payload.last_name.strip()}".strip(),
        email=email,
        password_hash=hash_password(payload.password),
        active=True,
        synthetic=True,
    )
    session.add(user)
    await session.flush()
    await set_request_context(session, user_id=user.id, institution_id=institution.id)
    session.add(
        InstitutionMembership(
            id=uuid.uuid4(),
            institution_id=institution.id,
            user_id=user.id,
            status="active",
        )
    )
    session.add(
        UserRoleAssignment(
            id=uuid.uuid4(),
            institution_id=institution.id,
            user_id=user.id,
            role_id=role.id,
        )
    )
    user_id = user.id
    display_name = user.display_name
    email_value = user.email
    subject = user.external_subject
    institution_id = institution.id
    institution_name = institution.name
    institution_slug = institution.slug
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists") from exc

    token = issue_demo_token(subject=subject, institution_id=institution_id, settings=settings)
    return SessionResponse(
        access_token=token,
        user_id=user_id,
        display_name=display_name,
        email=email_value,
        institution_id=institution_id,
        institution_name=institution_name,
        institution_slug=institution_slug,
        roles=[role_code],
        permissions=sorted(effective_permissions([role_code])),
        auth_mode="demo",
        synthetic=True,
    )


@router.get("/me", response_model=SessionResponse)
async def me(
    context: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> SessionResponse:
    institution = await session.get(Institution, context.institution_id)
    if institution is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    settings = get_settings()
    return SessionResponse(
        access_token="",
        user_id=context.user_id,
        display_name=context.display_name,
        email=context.email,
        institution_id=context.institution_id,
        institution_name=institution.name,
        institution_slug=institution.slug,
        roles=list(context.role_codes),
        permissions=sorted(effective_permissions(context.role_codes)),
        auth_mode=settings.auth_mode,
        synthetic=True,
    )

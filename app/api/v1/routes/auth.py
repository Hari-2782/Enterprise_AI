from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import (
    AuthenticatedUser,
    create_access_token,
    get_current_user,
    verify_password,
)
from app.database.connection import get_db
from app.database.models import User
from app.services.governance.audit import record_audit_event


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfileResponse(BaseModel):
    user_id: UUID
    email: str
    department: str
    roles: list[str]


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User)
        .options(selectinload(User.roles))
        .where(User.email == payload.email.strip().lower())
    )
    if user is None or not user.is_active or not verify_password(
        payload.password, user.password_hash
    ):
        record_audit_event(
            db,
            request_id=request.state.request_id,
            user_id=user.id if user else None,
            action="auth.login",
            resource_type="user",
            resource_id=payload.email.strip().lower(),
            outcome="denied",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    auth_user = AuthenticatedUser(
        user_id=user.id,
        email=user.email,
        department=user.department,
        roles=frozenset(role.name for role in user.roles),
    )
    record_audit_event(
        db,
        request_id=request.state.request_id,
        user_id=user.id,
        action="auth.login",
        resource_type="user",
        resource_id=str(user.id),
        outcome="allowed",
    )
    return TokenResponse(access_token=create_access_token(auth_user))


@router.get("/me", response_model=UserProfileResponse)
def current_profile(user: AuthenticatedUser = Depends(get_current_user)):
    return UserProfileResponse(
        user_id=user.user_id,
        email=user.email,
        department=user.department,
        roles=sorted(user.roles),
    )

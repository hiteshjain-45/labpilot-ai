"""Registration (students) and login (students and teachers)."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.limits import login_failures
from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.services import accounts
from app.utils.timeutil import utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Verifying against this hash for unknown emails keeps response time similar for both cases.
_DUMMY_HASH = hash_password("not-a-real-password")


def _token_response(db: Session, user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.role_name),
        user=UserOut(**accounts.user_profile(db, user)),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Self-registration creates student accounts only; teacher accounts are created by a teacher."""
    student = accounts.create_student(db, body.email, body.password, body.full_name, body.roll_number, body.cohort)
    student.user.last_login_at = utcnow()
    db.commit()
    return _token_response(db, student.user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    key = f"{request.client.host if request.client else 'unknown'}:{body.email}"
    if login_failures.is_blocked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed sign-in attempts. Try again in a few minutes.")
    user = db.scalar(select(User).where(User.email == body.email))
    valid = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not valid or not user.is_active:
        login_failures.hit(key)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Incorrect email or password", headers={"WWW-Authenticate": "Bearer"}
        )
    login_failures.reset(key)
    user.last_login_at = utcnow()
    db.commit()
    return _token_response(db, user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return UserOut(**accounts.user_profile(db, user))

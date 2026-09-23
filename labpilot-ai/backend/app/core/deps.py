"""FastAPI dependencies: current user, role guards and pagination helpers."""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import get_db
from app.models import Student, Teacher, User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized
    try:
        payload = decode_access_token(creds.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


def get_current_student(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Student:
    if user.role_name != "student":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This action is only available to students")
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Student profile not found")
    return student


def get_current_teacher(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Teacher:
    if user.role_name != "teacher":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This action is only available to teachers")
    teacher = db.scalar(select(Teacher).where(Teacher.user_id == user.id))
    if teacher is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Teacher profile not found")
    return teacher


def execution_guard(student: Student = Depends(get_current_student)) -> Student:
    """Student dependency for endpoints that execute code or call the AI provider: per-student rate limit."""
    from app.core.limits import execution_limiter

    if not execution_limiter.allow(f"student:{student.id}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "You are sending requests too quickly. Please wait a moment.")
    return student

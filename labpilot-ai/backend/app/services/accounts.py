"""Account creation shared by the API and the seed script."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import hash_password
from app.models import Role, Student, Teacher, User

ROLE_NAMES = ("student", "teacher")


def ensure_roles(db: Session) -> dict[str, Role]:
    existing = {r.name: r for r in db.scalars(select(Role))}
    for name in ROLE_NAMES:
        if name not in existing:
            role = Role(name=name)
            db.add(role)
            existing[name] = role
    db.flush()
    return existing


def email_taken(db: Session, email: str) -> bool:
    return db.scalar(select(User.id).where(User.email == email)) is not None


def _create_user(db: Session, email: str, password: str, full_name: str, role_name: str) -> User:
    if email_taken(db, email):
        raise AppError(409, "An account with this email already exists")
    roles = ensure_roles(db)
    user = User(email=email, full_name=full_name, password_hash=hash_password(password), role_id=roles[role_name].id)
    db.add(user)
    db.flush()
    return user


def create_student(
    db: Session, email: str, password: str, full_name: str,
    roll_number: Optional[str] = None, cohort: Optional[str] = None,
) -> Student:
    user = _create_user(db, email, password, full_name, "student")
    student = Student(user_id=user.id, roll_number=(roll_number or None), cohort=(cohort or None))
    db.add(student)
    db.flush()
    db.refresh(user)
    return student


def create_teacher(db: Session, email: str, password: str, full_name: str, department: Optional[str] = None) -> Teacher:
    user = _create_user(db, email, password, full_name, "teacher")
    teacher = Teacher(user_id=user.id, department=(department or None))
    db.add(teacher)
    db.flush()
    db.refresh(user)
    return teacher


def user_profile(db: Session, user: User) -> dict:
    """Flat profile dict used by the UserOut schema."""
    data = {
        "id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role_name,
        "roll_number": None, "cohort": None, "department": None, "created_at": user.created_at,
    }
    if user.role_name == "student":
        s = db.scalar(select(Student).where(Student.user_id == user.id))
        if s:
            data["roll_number"], data["cohort"] = s.roll_number, s.cohort
    else:
        t = db.scalar(select(Teacher).where(Teacher.user_id == user.id))
        if t:
            data["department"] = t.department
    return data

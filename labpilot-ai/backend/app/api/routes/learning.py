"""Mistake DNA, Skill Passport and adaptive recommendations for the signed-in student."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_student
from app.database import get_db
from app.models import ExperimentRecommendation, Student
from app.services import mistakes as mistake_service
from app.services import recommendation as reco_service
from app.services import skills as skill_service
from app.services import views

mistakes_router = APIRouter(prefix="/api/mistakes", tags=["mistakes"])
skills_router = APIRouter(prefix="/api/skills", tags=["skills"])
reco_router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@mistakes_router.get("/me")
def my_mistakes(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    profile = mistake_service.mistake_profile(db, student.id)
    return {**profile, "recent": mistake_service.recent_mistakes(db, student.id, limit=10)}


@skills_router.get("/me")
def my_skills(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    return skill_service.get_passport(db, student.id)


@reco_router.get("/me")
def current(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    """The current recommendation with its explanation (None once every experiment is mastered)."""
    rec = reco_service.current_recommendation(db, student.id)
    db.commit()
    return {"recommendation": views.serialize_recommendation(db, rec)}


@reco_router.post("/me/refresh")
def refresh(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    rec = reco_service.refresh_recommendation(db, student.id)
    db.commit()
    return {"recommendation": views.serialize_recommendation(db, rec)}


@reco_router.get("/me/history")
def history(limit: int = Query(default=20, ge=1, le=100), student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ExperimentRecommendation).where(ExperimentRecommendation.student_id == student.id)
        .order_by(ExperimentRecommendation.created_at.desc(), ExperimentRecommendation.id.desc()).limit(limit)
    ).all()
    return [views.serialize_recommendation(db, r) for r in rows]


@skills_router.get("/me/passport")
def my_skill_passport(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    """The Skill Passport page: profile, progress, skills and the Mistake DNA links, all derived on read."""
    return skill_service.passport_page(db, student)

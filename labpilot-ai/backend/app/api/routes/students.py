"""Student-facing aggregates: dashboard and progress."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_student
from app.database import get_db
from app.models import Student
from app.services import analytics

router = APIRouter(prefix="/api/students", tags=["students"])


@router.get("/me/dashboard")
def dashboard(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    data = analytics.student_dashboard(db, student)
    db.commit()  # the recommendation may have been refreshed
    return data

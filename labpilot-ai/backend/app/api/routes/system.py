"""Health and transparency endpoints."""
from fastapi import APIRouter, Depends

from app.ai.factory import get_provider
from app.core.constants import CATEGORIES, DIFFICULTIES, SKILLS, TEST_KINDS
from app.core.deps import get_current_user
from app.sandbox import get_sandbox

router = APIRouter(prefix="/api", tags=["system"])

VERSION = "0.1.0"


@router.get("/health")
def health():
    return {"status": "ok", "version": VERSION}


@router.get("/system/status", dependencies=[Depends(get_current_user)])
def system_status():
    """What the AI layer and the sandbox are actually doing (shown in the UI so nothing is hidden)."""
    return {"version": VERSION, "ai": get_provider().describe(), "sandbox": get_sandbox().describe()}


@router.get("/system/taxonomy", dependencies=[Depends(get_current_user)])
def taxonomy():
    """Skills, mistake categories and levels, so the teacher UI never hard-codes them."""
    return {
        "difficulties": DIFFICULTIES,
        "test_kinds": TEST_KINDS,
        "skills": list(SKILLS),
        "categories": [{"key": key, "label": meta["label"]} for key, meta in CATEGORIES.items()],
    }

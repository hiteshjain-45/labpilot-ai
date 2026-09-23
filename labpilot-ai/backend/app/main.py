"""FastAPI application entry point."""
import logging
import os
from contextlib import asynccontextmanager

from pathlib import Path

from sqlalchemy import func, select
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from app.api.routes import api_router
from app.config import DEFAULT_SECRET, get_settings, validate_settings
from app.core.errors import AppError
from app.database import SessionLocal, init_db
from app.sandbox import SandboxBusyError, SandboxError
from app.models import User
from app.services.accounts import ensure_roles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("labpilot")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    validate_settings(settings)
    init_db()
    with SessionLocal() as db:
        ensure_roles(db)
        db.commit()
    with SessionLocal() as db:
        if not db.scalar(select(func.count()).select_from(User)):
            log.warning("The database has no accounts yet. Create the demo data with: python -m app.seed")
    if settings.secret_key == DEFAULT_SECRET:
        log.warning("SECRET_KEY is the built-in development value. Set SECRET_KEY before any real deployment.")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        log.warning("The server is running as root, so the code sandbox cannot limit process creation. Run it as a normal user (see docs/SECURITY.md).")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="LabPilot AI", version="0.1.0", lifespan=lifespan,
        description="Intelligent Virtual Lab Management System - prototype v0.1",
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")  # never cache personal data or tokens
        return response

    @app.exception_handler(OverflowError)
    async def out_of_range_id(request: Request, exc: OverflowError):
        # An id larger than the database's integer column can hold cannot name an existing row, so this is a
        # plain "not found" rather than a server fault. SQLite raises it while binding the parameter.
        log.info("Out-of-range identifier in %s", request.url.path)
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(SandboxBusyError)
    async def sandbox_busy(_: Request, exc: SandboxBusyError):
        return JSONResponse(status_code=503, content={"detail": "The code runner is busy. Please try again in a moment."}, headers={"Retry-After": "3"})

    @app.exception_handler(SandboxError)
    async def sandbox_error(_: Request, exc: SandboxError):
        log.error("Sandbox failure: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "The code runner failed to start. Check the server logs."})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server. Please try again."})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # Flatten pydantic errors into one readable sentence for the UI, keep the details for tooling.
        errors = exc.errors()
        first = errors[0] if errors else {}
        field = ".".join(str(p) for p in first.get("loc", ()) if p not in ("body", "query", "path"))
        message = str(first.get("msg", "Invalid request")).removeprefix("Value error, ")
        return JSONResponse(
            status_code=422,
            content={"detail": f"{field}: {message}" if field else message, "errors": [
                {"field": ".".join(str(p) for p in e.get("loc", ())), "message": e.get("msg", "")} for e in errors
            ]},
        )

    app.include_router(api_router)
    return app


app = create_app()


# ---------------------------------------------------------------- built frontend (optional)
# After `npm run build` the API also serves the single-page app, so a demo needs only one process.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (FRONTEND_DIST / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/{path:path}", include_in_schema=False)
    def single_page_app(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (FRONTEND_DIST / path).resolve()
        if path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")

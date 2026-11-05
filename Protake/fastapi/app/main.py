"""Protake backend entrypoint: a single FastAPI application
serving the full AI Construction Quantity Takeoff API.
"""

import logging
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app import models  # noqa: F401  registers all tables on Base.metadata
from app.trades.pricing_service import PricingService

settings = get_settings()

logging.basicConfig(level=logging.INFO if not settings.debug else logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("protake")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Dev convenience: SQLite/first-run projects get their schema created
    # automatically. Postgres/production deployments should rely on
    # `alembic upgrade head` instead (this call is a safe no-op then,
    # since the tables already exist).
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        PricingService(db).seed_defaults_if_missing()
        db.commit()
    finally:
        db.close()

    # Heavy per-page work (Hough transform, PaddleOCR) is CPU-bound Python —
    # running it in a background *thread* (the old BackgroundTasks approach)
    # still holds the GIL for the whole page, so the server can't even
    # answer a health check while one page is processing. A real OS process
    # is immune to that; workers are spawned lazily on first use and reused
    # for every blueprint after, so model-loading cost (PaddleOCR, YOLO) is
    # only paid once per worker, not once per page.
    _app.state.process_pool = ProcessPoolExecutor(max_workers=2)

    logger.info("Protake backend ready (%s environment, database=%s)", settings.environment, "sqlite" if settings.is_sqlite else "postgresql")
    yield
    _app.state.process_pool.shutdown(wait=False, cancel_futures=True)


app = FastAPI(
    title="Protake API",
    description="AI-powered enterprise construction quantity takeoff backend.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "errors": exc.errors()},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/health", tags=["System"])
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


app.include_router(api_router, prefix=settings.api_v1_prefix)

from fastapi import APIRouter

from app.api.v1.endpoints import (
    assistant,
    audit,
    auth,
    estimates,
    ifc,
    pdf,
    projects,
    reports,
    takeoffs,
    trades,
    # --- Frozen / Legacy PDF Adapters (Bypassed in IFC-First Mode) ---
    # blueprints,
    # detections,
    # ground_truth,
    # measurements,
    # pages,
    # qa,
    # roofing,
    # schedule_items,
)

api_router = APIRouter()

# Core Authentication & Projects
api_router.include_router(auth.router)
api_router.include_router(projects.router)

# Primary Native Model Ingestion & QTO Engines (IFC + Native Vector PDF)
api_router.include_router(ifc.router)
api_router.include_router(pdf.router)

# Commercial, Trades & Estimation
api_router.include_router(trades.router)
api_router.include_router(takeoffs.router)
api_router.include_router(estimates.router)
api_router.include_router(reports.router)
api_router.include_router(audit.router)
api_router.include_router(assistant.router)

# --- Frozen / Legacy PDF & Vision Pipeline Routes (Commented out for IFC Phase) ---
# api_router.include_router(blueprints.router)
# api_router.include_router(pages.router)
# api_router.include_router(detections.router)
# api_router.include_router(schedule_items.router)
# api_router.include_router(measurements.router)
# api_router.include_router(ground_truth.router)
# api_router.include_router(qa.router)
# api_router.include_router(roofing.router, prefix="/roofing", tags=["roofing"])

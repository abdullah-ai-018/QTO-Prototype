"""app.py: FastAPI Application Entry Point & CAD Workbench API.

Implements REST and Server-Sent Events (SSE) endpoints matching PROJECT.md interface contracts:
- POST /api/upload: Multipart PDF upload
- POST /api/process/{file_id}: Initiates pipeline background execution
- GET /api/pipeline/events/{run_id}: SSE stream emitting pipeline progression (S00 to S16)
- GET /api/pipeline/status/{run_id}: Execution status & summary metrics
- GET /api/takeoff/{run_id}/summary: Takeoff metrics JSON
- GET /api/takeoff/{run_id}/walls: Traced wall runs, geometries, coordinates, tags
- GET /api/takeoff/{run_id}/export/excel: Streams generated qto.xlsx download
- GET /api/blueprint/{run_id}/annotated-pdf: Streams annotated PDF download
- GET /api/blueprint/{run_id}/page/{page_num}/image: Renders page PNG via PyMuPDF
- GET /: Serves CAD workbench SPA frontend from static/
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import threading
from typing import Any, Dict, List, Optional
import uuid

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
import pymupdf as fitz

from qto.geometry import Point, Segment
from qto.openings import Opening
from qto.dedup import WallRun
from qto.quantities import calculate_takeoff, TakeoffResult
from qto.export import export_takeoff_excel
from qto.pipeline import QTOPipeline

class ProcessRequest(BaseModel):
    selected_pages: Optional[List[int]] = None
    run_mode: Optional[str] = "floor_plans_only"
    default_height_ft: Optional[float] = None
    stud_spacing_in: Optional[int] = None
    waste_percent: Optional[float] = None

    model_config = ConfigDict(extra="allow")

class Point2D(BaseModel):
    x: float
    y: float

class CalibrationRequest(BaseModel):
    pt1: Point2D
    pt2: Point2D
    real_world_distance_ft: Optional[float] = None
    real_world_feet: Optional[float] = None
    dimension_string: Optional[str] = None
    unit: Optional[str] = "ft"

class CalibrationResponse(BaseModel):
    success: bool
    page_num: int
    measured_pixel_distance: float
    new_ft_per_pt: float
    recalculated_takeoff: Dict[str, Any]

class OpeningInput(BaseModel):
    type: Optional[str] = "door"
    width_ft: float = Field(default=3.0, gt=0, description="Opening width in feet must be positive")
    height_ft: Optional[float] = Field(default=7.0, gt=0, description="Opening height in feet must be positive")
    center_pt: Optional[Point2D] = None

class WallCreateRequest(BaseModel):
    start: Point2D
    end: Point2D
    tag: str = "1A"
    height_ft: Optional[float] = Field(default=10.0, gt=0, description="Wall height must be positive")
    openings: Optional[List[OpeningInput]] = None

CreateWallRequest = WallCreateRequest

class WallUpdateRequest(BaseModel):
    start: Optional[Point2D] = None
    end: Optional[Point2D] = None
    tag: Optional[str] = None
    height_ft: Optional[float] = Field(default=None, gt=0, description="Wall height must be positive")
    openings: Optional[List[OpeningInput]] = None
    thickness_in: Optional[float] = Field(default=None, gt=0, description="Wall thickness must be positive")
    thickness_measured: Optional[bool] = None
    is_height_verified: Optional[bool] = None
    height_source: Optional[str] = None
    status: Optional[str] = None
    gross_length_ft: Optional[float] = Field(default=None, gt=0)
    opening_deduction_ft: Optional[float] = Field(default=None, ge=0)

UpdateWallRequest = WallUpdateRequest

class RunUpdateRequest(WallUpdateRequest):
    run_id: str
    wall_id: str

class WallDeleteResponse(BaseModel):
    success: bool
    deleted_id: str
    recalculated_takeoff: Dict[str, Any]

# Working directories
BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
RUNS_DIR = BASE_DIR / "runs"
STATIC_DIR = BASE_DIR / "static"
FIXTURES_DIR = BASE_DIR / "tests" / "fixtures"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# In-memory tracking
RUNS: Dict[str, Dict[str, Any]] = {}
RUN_EVENT_QUEUES: Dict[str, List[asyncio.Queue]] = {}
UPLOADED_FILES: Dict[str, Dict[str, Any]] = {}
MAIN_LOOP: Optional[asyncio.AbstractEventLoop] = None
_RUN_LOCKS: Dict[str, threading.RLock] = {}
_RUN_LOCKS_GUARD = threading.Lock()

def _get_run_lock(run_id: str) -> threading.RLock:
    with _RUN_LOCKS_GUARD:
        if run_id not in _RUN_LOCKS:
            _RUN_LOCKS[run_id] = threading.RLock()
        return _RUN_LOCKS[run_id]


class ObservableQTOPipeline(QTOPipeline):
    """Subclass of QTOPipeline that dispatches real-time stage progress."""

    def __init__(self, *args, progress_callback=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.progress_callback = progress_callback

    def notify(self, stage: str, pct: int, msg: str):
        if self.progress_callback:
            try:
                self.progress_callback(stage, pct, msg)
            except Exception as e:
                print(f"[PROGRESS ERROR] {e}")

    def _stage_s00_run_setup(self):
        self.notify("S00", 5, "Initializing run and computing SHA-256 hash")
        super()._stage_s00_run_setup()

    def _stage_s01_sheet_indexing(self):
        self.notify("S01", 12, "Indexing blueprint pages & sheet labels")
        super()._stage_s01_sheet_indexing()

    def _stage_s02_tag_discovery(self):
        self.notify("S02", 20, "Discovering partition schedule tags with lumber exclusion")
        super()._stage_s02_tag_discovery()

    def _stage_s03_assembly_extraction(self):
        self.notify("S03", 28, "Extracting assembly material descriptions")
        super()._stage_s03_assembly_extraction()

    def _stage_s04_classification(self):
        self.notify("S04", 38, "Evaluating drywall assemblies with Jev AI classifier")
        super()._stage_s04_classification()

    def _stage_s05_assembly_attributes(self):
        self.notify("S05", 46, "Parsing wall assembly attributes (studs, spacing, layers)")
        super()._stage_s05_assembly_attributes()

    def _stage_s06_scale_calibration(self):
        self.notify("S06", 54, "Calibrating architectural scale and points-to-feet conversion")
        super()._stage_s06_scale_calibration()

    def _stage_s07_vector_extraction(self):
        self.notify("S07", 62, "Extracting CAD vector linework and door swing arcs")
        super()._stage_s07_vector_extraction()

    def _stage_s08_tag_instances(self):
        self.notify("S08", 70, "Locating qualified drywall tag callouts on floor plan sheets")
        super()._stage_s08_tag_instances()

    def _stage_s09_to_s12_wall_tracing(self):
        self.notify("S09-S12", 80, "Tracing wall runs, leader endpoints, and door deductions")
        super()._stage_s09_to_s12_wall_tracing()

    def _stage_s13_deduplication(self):
        self.notify("S13", 88, "Consolidating duplicate wall runs and resolving conflicts")
        super()._stage_s13_deduplication()

    def _stage_s13b_section_height_verification(self):
        self.notify("S13B", 91, "Verifying wall heights against section details and applying 10 ft fallback")
        super()._stage_s13b_section_height_verification()

    def _stage_s14_takeoff_quantities(self):
        self.notify("S14", 94, "Calculating takeoff quantities (LF, SF, studs, track, consumables)")
        super()._stage_s14_takeoff_quantities()

    def _stage_s15_export_output(self):
        self.notify("S15", 97, "Exporting 7-sheet openpyxl Excel workbook (qto.xlsx)")
        super()._stage_s15_export_output()

    def _stage_s16_annotate_pdf(self):
        self.notify("S16", 100, "Rendering dual-red vector annotated blueprint PDF")
        super()._stage_s16_annotate_pdf()


def dispatch_event(run_id: str, event_type: str, data: Dict[str, Any]):
    """Thread-safe event dispatcher for SSE streams."""
    item = {"event": event_type, "data": data}
    if run_id in RUNS:
        RUNS[run_id]["events"].append(item)

    queues = RUN_EVENT_QUEUES.get(run_id, [])
    if MAIN_LOOP and not MAIN_LOOP.is_closed():
        for q in queues:
            try:
                MAIN_LOOP.call_soon_threadsafe(q.put_nowait, item)
            except Exception:
                pass


def _run_pipeline_worker(
    run_id: str,
    pdf_path: str,
    config: Dict[str, Any],
    selected_pages: Optional[List[int]] = None,
):
    """Background worker function executing the full QTO pipeline."""
    output_dir = str(RUNS_DIR / run_id)
    os.makedirs(output_dir, exist_ok=True)

    # Cache source PDF in run directory
    try:
        shutil.copy2(pdf_path, os.path.join(output_dir, "source.pdf"))
    except Exception:
        pass

    def on_progress(stage: str, pct: int, msg: str):
        if run_id in RUNS:
            RUNS[run_id]["progress_pct"] = pct
            RUNS[run_id]["stage"] = stage
            RUNS[run_id]["message"] = msg
        dispatch_event(
            run_id,
            "progress",
            {"stage": stage, "progress_pct": pct, "message": msg},
        )

    try:
        pipeline = ObservableQTOPipeline(
            pdf_path=pdf_path,
            run_id=run_id,
            output_dir=output_dir,
            config=config,
            selected_pages=selected_pages,
            progress_callback=on_progress,
        )
        summary = pipeline.run()

        if run_id in RUNS:
            RUNS[run_id]["status"] = "completed"
            RUNS[run_id]["progress_pct"] = 100
            RUNS[run_id]["stage"] = "S16: Complete"
            RUNS[run_id]["message"] = "Drywall QTO pipeline execution completed successfully."
            RUNS[run_id]["summary"] = summary

        dispatch_event(
            run_id,
            "complete",
            {
                "run_id": run_id,
                "status": "completed",
                "summary_url": f"/api/takeoff/{run_id}/summary",
            },
        )
    except Exception as e:
        err_msg = str(e)
        if run_id in RUNS:
            RUNS[run_id]["status"] = "error"
            RUNS[run_id]["error"] = err_msg
            RUNS[run_id]["message"] = f"Pipeline execution failed: {err_msg}"

        dispatch_event(
            run_id,
            "error",
            {"run_id": run_id, "status": "error", "message": err_msg},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager to capture running event loop."""
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="PDF ENGINE - Drywall QTO Workbench API",
    version="1.0.0",
    description="Automated Drywall Quantity Takeoff CAD Workbench API",
    lifespan=lifespan,
)

# Enable CORS for workbench clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    for err in exc.errors():
        loc = err.get("loc", ())
        err_type = err.get("type", "")
        if "height_ft" in loc and any(c in err_type for c in ("greater_than", "greater_than_equal", "value_error")):
            return JSONResponse(status_code=400, content={"detail": "Wall height must be positive"})
        if "width_ft" in loc and any(c in err_type for c in ("greater_than", "greater_than_equal", "value_error")):
            return JSONResponse(status_code=400, content={"detail": "Opening width must be positive"})
        if "page_num" in loc and any(c in err_type for c in ("greater_than", "greater_than_equal", "value_error")):
            return JSONResponse(status_code=400, content={"detail": "Page number must be positive (>= 1)"})
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


# =============================================================================
# REST API ENDPOINTS
# =============================================================================


@app.post("/api/upload")
async def upload_blueprint(file: UploadFile = File(...)):
    """Multipart file upload for blueprint PDFs.

    Validates extension and PyMuPDF parseability.
    """
    filename = file.filename or "blueprint.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Only blueprint PDF files (.pdf) are supported.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        with fitz.open(stream=content, filetype="pdf") as doc:
            page_count = len(doc)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Uploaded file could not be parsed as a valid PDF document: {e}",
        )

    file_id = f"doc_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    dest_path = UPLOADS_DIR / f"{file_id}.pdf"
    dest_path.write_bytes(content)

    meta = {
        "file_id": file_id,
        "filename": filename,
        "page_count": page_count,
        "file_size": len(content),
        "path": str(dest_path),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    UPLOADED_FILES[file_id] = meta

    return {
        "file_id": file_id,
        "filename": filename,
        "page_count": page_count,
        "file_size": len(content),
    }


@app.post("/api/process/{file_id}", status_code=202)
async def process_blueprint(
    file_id: str,
    request: Optional[ProcessRequest] = Body(default=None),
):
    """Initiates background QTO pipeline execution for an uploaded file."""
    # 1. Resolve source PDF path
    source_path = UPLOADS_DIR / f"{file_id}.pdf"
    if not source_path.exists():
        # Check if file_id corresponds to a known fixture
        candidate_fixtures = [
            FIXTURES_DIR / f"{file_id}.pdf",
            FIXTURES_DIR / file_id,
            BASE_DIR / file_id,
        ]
        found = False
        for cand in candidate_fixtures:
            if cand.exists():
                source_path = cand
                found = True
                break
        if not found:
            raise HTTPException(
                status_code=404,
                detail=f"Blueprint file '{file_id}' not found.",
            )

    req = request or ProcessRequest()
    selected_pages = req.selected_pages
    config = req.model_dump(exclude={"selected_pages"}, exclude_none=True)

    # 2. Allocate run_id
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    run_id = f"run_{timestamp_str}_{short_id}"

    RUNS[run_id] = {
        "run_id": run_id,
        "file_id": file_id,
        "pdf_path": str(source_path),
        "status": "processing",
        "selected_pages": selected_pages,
        "progress_pct": 0,
        "stage": "S00: Initializing",
        "message": "Pipeline queued for execution",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "events": [],
        "error": None,
    }

    # 3. Start worker thread
    t = threading.Thread(
        target=_run_pipeline_worker,
        args=(run_id, str(source_path), config, selected_pages),
        daemon=True,
    )
    t.start()

    return {
        "run_id": run_id,
        "file_id": file_id,
        "status": "processing",
        "selected_pages": selected_pages,
        "message": "Pipeline processing started.",
    }


@app.get("/api/pipeline/events/{run_id}")
async def stream_pipeline_events(run_id: str):
    """Server-Sent Events (SSE) stream emitting real-time stage progression."""
    # Verify run exists or was completed
    disk_output = RUNS_DIR / run_id / "output.json"
    if run_id not in RUNS and not disk_output.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Run '{run_id}' not found.",
        )

    async def event_generator():
        q: asyncio.Queue = asyncio.Queue()
        if run_id not in RUN_EVENT_QUEUES:
            RUN_EVENT_QUEUES[run_id] = []
        RUN_EVENT_QUEUES[run_id].append(q)

        try:
            # Emit existing history
            if run_id in RUNS:
                for ev in RUNS[run_id]["events"]:
                    event_type = ev.get("event", "progress")
                    data_str = json.dumps(ev.get("data", {}))
                    yield f"event: {event_type}\ndata: {data_str}\n\n"

                if RUNS[run_id]["status"] == "completed":
                    yield (
                        f"event: complete\ndata: {json.dumps({'run_id': run_id, 'status': 'completed', 'summary_url': f'/api/takeoff/{run_id}/summary'})}\n\n"
                    )
                    return
                elif RUNS[run_id]["status"] == "error":
                    yield (
                        f"event: error\ndata: {json.dumps({'run_id': run_id, 'status': 'error', 'message': RUNS[run_id].get('error', 'Error')})}\n\n"
                    )
                    return
            elif disk_output.exists():
                yield (
                    f"event: complete\ndata: {json.dumps({'run_id': run_id, 'status': 'completed', 'summary_url': f'/api/takeoff/{run_id}/summary'})}\n\n"
                )
                return

            # Wait for live events
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=1.0)
                    event_type = item.get("event", "progress")
                    data_str = json.dumps(item.get("data", {}))
                    yield f"event: {event_type}\ndata: {data_str}\n\n"
                    if event_type in ("complete", "error"):
                        break
                except asyncio.TimeoutError:
                    if run_id in RUNS and RUNS[run_id]["status"] in ("completed", "error"):
                        st = RUNS[run_id]["status"]
                        if st == "completed":
                            yield (
                                f"event: complete\ndata: {json.dumps({'run_id': run_id, 'status': 'completed', 'summary_url': f'/api/takeoff/{run_id}/summary'})}\n\n"
                            )
                        else:
                            yield (
                                f"event: error\ndata: {json.dumps({'run_id': run_id, 'status': 'error', 'message': RUNS[run_id].get('error')})}\n\n"
                            )
                        break
                    yield ": keepalive\n\n"
        finally:
            if run_id in RUN_EVENT_QUEUES and q in RUN_EVENT_QUEUES[run_id]:
                RUN_EVENT_QUEUES[run_id].remove(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/pipeline/status/{run_id}")
async def get_pipeline_status(run_id: str):
    """Returns execution status and summary metrics for a pipeline run."""
    if run_id in RUNS:
        r = RUNS[run_id]
        return {
            "run_id": run_id,
            "status": r["status"],
            "progress_pct": r["progress_pct"],
            "current_stage": r["stage"],
            "message": r.get("message", ""),
            "error": r.get("error"),
        }

    disk_output = RUNS_DIR / run_id / "output.json"
    if disk_output.exists():
        return {
            "run_id": run_id,
            "status": "completed",
            "progress_pct": 100,
            "current_stage": "S16: Complete",
            "message": "Pipeline execution completed.",
            "error": None,
        }

    raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")


@app.get("/api/takeoff/latest")
async def get_latest_takeoff(blueprint_file: Optional[str] = None):
    """Returns the most recent completed takeoff run with detected walls."""
    run_folders = sorted(RUNS_DIR.glob("run_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for rf in run_folders:
        out = rf / "output.json"
        if out.exists():
            try:
                with open(out, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    if blueprint_file and blueprint_file not in d.get("pdf_file", ""):
                        continue
                    if d.get("total_wall_runs", 0) > 0:
                        d["artifacts"] = {
                            "annotated_pdf_url": f"/api/blueprint/{rf.name}/annotated-pdf",
                            "excel_workbook_url": f"/api/takeoff/{rf.name}/export/excel",
                        }
                        return {"run_id": rf.name, "summary": d}
            except Exception:
                continue
    raise HTTPException(status_code=404, detail="No completed takeoff runs found.")


@app.get("/api/takeoff/{run_id}")
async def get_takeoff_full(run_id: str):
    """Returns combined takeoff summary, walls with thickness/layers, and review items matching contract."""
    output_json = RUNS_DIR / run_id / "output.json"
    if not output_json.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Takeoff for run '{run_id}' not found.",
        )

    with open(output_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    runs = data.get("runs", [])
    verified_count = sum(1 for r in runs if r.get("is_height_verified", False))
    unverified_count = len(runs) - verified_count

    summary = {
        "total_gross_lf": data.get("total_gross_lf", 0.0),
        "total_net_lf": data.get("total_net_lf", 0.0),
        "total_board_sf": data.get("total_board_sf", 0.0),
        "total_walls": len(runs),
        "verified_height_count": verified_count,
        "unverified_height_count": unverified_count,
    }

    return {
        "run_id": run_id,
        "summary": summary,
        "walls": runs,
        "review_items": data.get("review_items", []),
    }


@app.get("/api/takeoff")
async def get_takeoff_query(run_id: Optional[str] = Query(default=None)):
    """Returns takeoff data for specified run_id or latest completed run."""
    if run_id:
        return await get_takeoff_full(run_id)
    return await get_latest_takeoff()


@app.get("/api/sheets")
async def get_sheets_query(
    file_id: Optional[str] = Query(default=None),
    run_id: Optional[str] = Query(default=None),
):
    """Convenience alias returning sheet catalog for file_id or run_id."""
    target_id = file_id or run_id
    if not target_id:
        run_folders = sorted(RUNS_DIR.glob("run_*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if run_folders:
            target_id = run_folders[0].name
        else:
            raise HTTPException(status_code=400, detail="Either file_id or run_id must be provided")

    run_output = RUNS_DIR / target_id / "output.json"
    if run_output.exists():
        try:
            with open(run_output, "r", encoding="utf-8") as f:
                d = json.load(f)
            if "sheets" in d and isinstance(d["sheets"], list) and len(d["sheets"]) > 0:
                return d["sheets"]
            if "file_id" in d:
                return await get_blueprint_sheet_catalog(d["file_id"])
            if "pdf_file" in d:
                return await get_blueprint_sheet_catalog(d["pdf_file"])
        except Exception:
            pass

    if run_id and run_id in RUNS and "file_id" in RUNS[run_id]:
        return await get_blueprint_sheet_catalog(RUNS[run_id]["file_id"])

    return await get_blueprint_sheet_catalog(target_id)


@app.get("/api/takeoff/{run_id}/summary")
async def get_takeoff_summary(run_id: str):
    """Returns takeoff metrics JSON for dashboard cards and bottom schedule dock."""
    output_json = RUNS_DIR / run_id / "output.json"
    if not output_json.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Takeoff summary for run '{run_id}' not found.",
        )

    with open(output_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["artifacts"] = {
        "annotated_pdf_url": f"/api/blueprint/{run_id}/annotated-pdf",
        "excel_workbook_url": f"/api/takeoff/{run_id}/export/excel",
    }
    return data


@app.get("/api/takeoff/{run_id}/walls")
async def get_takeoff_walls(run_id: str, tag: Optional[str] = None):
    """Returns list of detected wall runs, geometries, coordinates, and tags for Inspector."""
    output_json = RUNS_DIR / run_id / "output.json"
    if not output_json.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Wall data for run '{run_id}' not found.",
        )

    with open(output_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    runs = data.get("runs", [])
    if tag:
        runs = [r for r in runs if r.get("tag") == tag]

    return {
        "run_id": run_id,
        "total_walls": len(runs),
        "walls": runs,
    }


@app.get("/api/takeoff/{run_id}/export/excel")
async def download_takeoff_excel(run_id: str):
    """Streams generated 7-sheet qto.xlsx workbook download."""
    excel_path = RUNS_DIR / run_id / "qto.xlsx"
    if not excel_path.exists():
        output_json = RUNS_DIR / run_id / "output.json"
        if output_json.exists():
            try:
                with open(output_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                recalculate_run_state(run_id, data)
            except Exception as e:
                print(f"[EXCEL DOWNLOAD] Warning: On-demand excel generation failed: {e}")

    if not excel_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Takeoff Excel file for run '{run_id}' not found.",
        )

    return FileResponse(
        path=str(excel_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"qto_{run_id}.xlsx",
    )


@app.get("/api/blueprint/{run_id}/annotated-pdf")
async def download_annotated_pdf(run_id: str):
    """Streams generated annotated PDF file download."""
    pdf_path = RUNS_DIR / run_id / "annotated.pdf"
    if not pdf_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Annotated PDF file for run '{run_id}' not found.",
        )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"annotated_{run_id}.pdf",
    )


@app.get("/api/blueprint/{run_id}/page/{page_num}/image")
async def render_blueprint_page_image(
    run_id: str,
    page_num: int,
    mode: str = Query(default="overlay", pattern="^(overlay|raw|clean)$"),
    dpi: int = Query(default=150, ge=72, le=300),
):
    """Renders a blueprint page as PNG via PyMuPDF for high-res canvas viewing."""
    pdf_path: Optional[str] = None

    if mode == "raw":
        if run_id in RUNS and os.path.exists(RUNS[run_id].get("pdf_path", "")):
            pdf_path = RUNS[run_id]["pdf_path"]
        elif (RUNS_DIR / run_id / "source.pdf").exists():
            pdf_path = str(RUNS_DIR / run_id / "source.pdf")

    if not pdf_path:
        # Default to annotated PDF if available
        annotated = RUNS_DIR / run_id / "annotated.pdf"
        if annotated.exists() and mode != "raw":
            pdf_path = str(annotated)
        elif run_id in RUNS and os.path.exists(RUNS[run_id].get("pdf_path", "")):
            pdf_path = RUNS[run_id]["pdf_path"]
        elif (RUNS_DIR / run_id / "source.pdf").exists():
            pdf_path = str(RUNS_DIR / run_id / "source.pdf")
        elif (RUNS_DIR / run_id / "output.json").exists():
            with open(RUNS_DIR / run_id / "output.json", "r", encoding="utf-8") as f:
                info = json.load(f)
            pdf_file = info.get("pdf_file", "")
            if (UPLOADS_DIR / pdf_file).exists():
                pdf_path = str(UPLOADS_DIR / pdf_file)
            elif (FIXTURES_DIR / pdf_file).exists():
                pdf_path = str(FIXTURES_DIR / pdf_file)

    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(
            status_code=404,
            detail=f"Blueprint PDF file for run '{run_id}' not found.",
        )

    try:
        with fitz.open(pdf_path) as doc:
            page_count = len(doc)
            page_idx = page_num - 1
            if page_idx < 0 or page_idx >= page_count:
                raise HTTPException(
                    status_code=404,
                    detail=f"Page {page_num} is out of bounds (document has {page_count} pages).",
                )
            page = doc[page_idx]
            pix = page.get_pixmap(dpi=dpi)
            png_bytes = pix.tobytes("png")
        return Response(content=png_bytes, media_type="image/png")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to render blueprint page: {e}",
        )


@app.get("/api/blueprint/{file_id}/sheets")
async def get_blueprint_sheet_catalog(file_id: str):
    """Fast sheet catalog endpoint returning sheet numbers, titles, and scales."""
    # 1. Tier 1: In-memory cache
    if file_id in UPLOADED_FILES and "sheets_catalog" in UPLOADED_FILES[file_id]:
        return UPLOADED_FILES[file_id]["sheets_catalog"]

    # 2. Tier 2: Disk cache
    cache_file = UPLOADS_DIR / f"{file_id}_sheets.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                catalog = json.load(f)
            if file_id in UPLOADED_FILES:
                UPLOADED_FILES[file_id]["sheets_catalog"] = catalog
            return catalog
        except Exception:
            pass

    # 3. Resolve PDF path
    source_path = None
    if file_id in RUNS and "pdf_path" in RUNS[file_id]:
        source_path = Path(RUNS[file_id]["pdf_path"])
    elif (UPLOADS_DIR / f"{file_id}.pdf").exists():
        source_path = UPLOADS_DIR / f"{file_id}.pdf"
    elif (UPLOADS_DIR / file_id).exists():
        source_path = UPLOADS_DIR / file_id
    else:
        candidate_fixtures = [
            FIXTURES_DIR / f"{file_id}.pdf",
            FIXTURES_DIR / file_id,
            BASE_DIR / file_id,
        ]
        for cand in candidate_fixtures:
            if cand.exists():
                source_path = cand
                break

    if not source_path or not source_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Blueprint file '{file_id}' not found.",
        )

    # 4. Generate catalog using qto.sheet_index
    try:
        from qto.sheet_index import extract_blueprint_sheet_catalog

        catalog = extract_blueprint_sheet_catalog(source_path)
        if file_id in UPLOADED_FILES:
            UPLOADED_FILES[file_id]["sheets_catalog"] = catalog
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(catalog, f, indent=2)
        except Exception:
            pass
        return catalog
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate sheet catalog for '{file_id}': {e}",
        )


# =============================================================================
# M2: SCALE CALIBRATION & WALL MARKUP CRUD ENDPOINTS
# =============================================================================

def _ensure_run_loaded(run_id: str) -> Dict[str, Any]:
    """Loads run output.json, auto-seeding test_run from test_run_door if required."""
    with _get_run_lock(run_id):
        run_dir = RUNS_DIR / run_id
        output_json = run_dir / "output.json"
        if not output_json.exists():
            if run_id == "test_run":
                source_door = RUNS_DIR / "test_run_door"
                if source_door.exists():
                    run_dir.mkdir(parents=True, exist_ok=True)
                    if (source_door / "output.json").exists():
                        shutil.copy(str(source_door / "output.json"), str(output_json))
                    if (source_door / "annotated.pdf").exists():
                        shutil.copy(str(source_door / "annotated.pdf"), str(run_dir / "annotated.pdf"))
            if not output_json.exists():
                raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

        with open(output_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data


def recalculate_run_state(run_id: str, data: Dict[str, Any]) -> TakeoffResult:
    """Recomputes all takeoff quantities, updates output.json, and re-exports qto.xlsx."""
    runs_raw = data.get("runs", [])
    sheets_raw = data.get("sheets", [])

    # Map sheets by page_num
    sheet_scales = {s["page_num"]: s.get("ft_per_pt", 0.111111) for s in sheets_raw}
    default_scale = sheets_raw[0].get("ft_per_pt", 0.111111) if sheets_raw else 0.111111

    # Reconstruct WallRun dataclass objects
    wall_runs: List[WallRun] = []
    for r in runs_raw:
        spine_dict = r.get("spine", {})
        spine = Segment(
            x1=float(spine_dict.get("x1", 0.0)),
            y1=float(spine_dict.get("y1", 0.0)),
            x2=float(spine_dict.get("x2", 0.0)),
            y2=float(spine_dict.get("y2", 0.0)),
        )
        p_num = int(r.get("page_num", 1))
        ft_pt = float(r.get("ft_per_pt", sheet_scales.get(p_num, default_scale)))

        openings_list: List[Opening] = []
        for op in r.get("openings", []):
            c_pt = None
            if op.get("center_pt"):
                c_pt = Point(float(op["center_pt"].get("x", 0.0)), float(op["center_pt"].get("y", 0.0)))
            openings_list.append(
                Opening(
                    opening_id=op.get("opening_id", f"OP-{r.get('run_id')}"),
                    wall_run_id=r.get("run_id", ""),
                    page_num=p_num,
                    t_start=float(op.get("t_start", 0.0)),
                    t_end=float(op.get("t_end", 0.0)),
                    width_pt=float(op.get("width_pt", 0.0)),
                    width_ft=float(op.get("width_ft", 0.0)),
                    height_ft=float(op.get("height_ft", 7.0)),
                    classification=op.get("classification", "CONFIRMED"),
                    evidence=op.get("evidence", "MANUAL_ESTIMATOR"),
                    center_pt=c_pt,
                )
            )

        gross_pt = float(r.get("gross_length_pt", spine.length))
        gross_ft = float(r.get("gross_length_ft", round(gross_pt * ft_pt, 2)))
        open_ft = float(r.get("opening_deduction_ft", round(sum(o.width_ft for o in openings_list), 2)))
        net_ft = float(r.get("net_length_ft", max(0.0, round(gross_ft - open_ft, 2))))

        wr = WallRun(
            run_id=r["run_id"],
            tag=r.get("tag", "1A"),
            page_num=p_num,
            sheet_label=r.get("sheet_label", f"Page_{p_num}"),
            spine=spine,
            gross_length_pt=gross_pt,
            gross_length_ft=gross_ft,
            opening_deduction_ft=open_ft,
            net_length_ft=net_ft,
            openings=openings_list,
            segments=[spine],
            tag_instances=r.get("tag_instances", []),
            status=r.get("status", "OK"),
            conflict_tags=r.get("conflict_tags", []),
            notes=r.get("notes", []),
            ft_per_pt=ft_pt,
            is_manual=bool(r.get("is_manual", False)),
            height_ft=float(r["height_ft"]) if r.get("height_ft") is not None else None,
            thickness_pt=float(r["thickness_pt"]) if r.get("thickness_pt") is not None else None,
            thickness_in=float(r["thickness_in"]) if r.get("thickness_in") is not None else None,
            thickness_measured=bool(r.get("thickness_measured", False)),
            section_callout_tag=r.get("section_callout_tag"),
            is_height_verified=bool(r.get("is_height_verified", False)),
            height_source=r.get("height_source", "UNVERIFIED_HEIGHT_DEFAULT"),
            material_layers=r.get("material_layers", []),
        )
        wall_runs.append(wr)

    # Extract assembly attributes from by_tag
    assembly_attributes = {}
    for tag, t_info in data.get("by_tag", {}).items():
        assembly_attributes[tag] = dict(t_info.get("attributes", {}))
        if "height_ft" in t_info:
            assembly_attributes[tag]["height_ft"] = t_info["height_ft"]

    # Compute takeoff
    takeoff_res = calculate_takeoff(
        runs=wall_runs,
        scale_ft_per_pt=default_scale,
        default_height_ft=float(data.get("default_height_ft", 10.0)),
        stud_spacing_in=int(data.get("stud_spacing_in", 16)),
        waste_percent=float(data.get("waste_percent", 0.0)),
        assembly_attributes=assembly_attributes,
    )

    # Update data dictionary
    all_openings = [op.to_dict() for wr in wall_runs for op in wr.openings]
    data["total_wall_runs"] = len(wall_runs)
    data["total_openings_deducted"] = len(all_openings)
    data["total_gross_lf"] = takeoff_res.total_gross_lf
    data["total_opening_deduction_lf"] = takeoff_res.total_opening_deduction_lf
    data["total_net_lf"] = takeoff_res.total_net_lf
    data["total_board_sf"] = takeoff_res.total_board_sf
    data["total_studs_ea"] = takeoff_res.total_studs_ea
    data["total_stud_lf"] = takeoff_res.total_stud_lf
    data["total_track_lf"] = takeoff_res.total_track_lf
    data["total_plates_lf"] = takeoff_res.total_plates_lf
    data["consumables"] = takeoff_res.consumables
    data["by_tag"] = {tag: t_sum.to_dict() for tag, t_sum in takeoff_res.by_tag.items()}
    data["openings"] = all_openings
    data["runs"] = [wr.to_dict() for wr in wall_runs]
    data["lines"] = [line.to_dict() for line in takeoff_res.lines]
    verified_count = sum(1 for wr in wall_runs if getattr(wr, "is_height_verified", False))
    unverified_count = len(wall_runs) - verified_count
    data["verified_height_count"] = verified_count
    data["unverified_height_count"] = unverified_count
    data["review_items"] = takeoff_res.review_items

    # Persist output.json and qto.xlsx atomically
    with _get_run_lock(run_id):
        output_json_path = RUNS_DIR / run_id / "output.json"
        temp_json_path = RUNS_DIR / run_id / "output.json.tmp"
        with open(temp_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temp_json_path, output_json_path)

        # Re-export qto.xlsx
        run_info = {
            "run_id": run_id,
            "pdf_file": data.get("pdf_file", "blueprint.pdf"),
            "pdf_sha256": data.get("pdf_sha256", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "default_height_ft": float(data.get("default_height_ft", 10.0)),
            "stud_spacing_in": int(data.get("stud_spacing_in", 16)),
        }
        excel_path = RUNS_DIR / run_id / "qto.xlsx"
        temp_excel_path = RUNS_DIR / run_id / "qto.xlsx.tmp"
        try:
            export_takeoff_excel(
                takeoff=takeoff_res,
                run_info=run_info,
                output_path=str(temp_excel_path),
            )
            os.replace(temp_excel_path, excel_path)
        except Exception as e:
            if temp_excel_path.exists():
                try:
                    temp_excel_path.unlink()
                except OSError:
                    pass
            print(f"[RECALCULATE] Warning: Excel export failed: {e}")

        # Refresh in-memory cache if tracked
        if run_id in RUNS:
            RUNS[run_id]["summary"] = data

    return takeoff_res


@app.post("/api/blueprint/{run_id}/page/{page_num}/calibrate", response_model=CalibrationResponse)
async def calibrate_page_scale(run_id: str, page_num: int, req: CalibrationRequest):
    """Calibrates scale from 2-point reference measurement and dynamically recalculates takeoff."""
    if page_num < 1:
        raise HTTPException(status_code=400, detail="Page number must be positive (>= 1)")

    with _get_run_lock(run_id):
        data = _ensure_run_loaded(run_id)

        existing_sheet_pages = {s.get("page_num") for s in data.get("sheets", []) if "page_num" in s}
        if existing_sheet_pages and page_num not in existing_sheet_pages:
            raise HTTPException(status_code=404, detail=f"Page {page_num} not found in run sheets")

        # 1. Calculate pixel distance
        dx = req.pt2.x - req.pt1.x
        dy = req.pt2.y - req.pt1.y
        pixel_distance = math.hypot(dx, dy)
        if pixel_distance <= 0:
            raise HTTPException(status_code=400, detail="Calibration points must not be identical")

        # 2. Resolve real-world distance in feet
        real_dist = req.real_world_distance_ft
        if real_dist is None:
            real_dist = req.real_world_feet
        if real_dist is None and req.dimension_string:
            val = req.dimension_string.strip()
            m_simple = re.match(r"^(\d+(?:\.\d+)?)\s*(?:ft|'|feet)?$", val, re.IGNORECASE)
            if m_simple and not ("-" in val or '"' in val):
                real_dist = float(m_simple.group(1))
            else:
                m_arch = re.match(
                    r"^(\d+(?:\.\d+)?)\s*(?:'|ft|feet)?\s*(?:-|\s)?\s*(?:(\d+(?:\.\d+)?)(?:\s+(\d+/\d+))?|(\d+/\d+))?\s*(?:\"|in|inches)?$",
                    val,
                    re.IGNORECASE,
                )
                if m_arch:
                    ft_part = float(m_arch.group(1))
                    in_part = 0.0
                    whole_in = m_arch.group(2)
                    frac_in = m_arch.group(3) or m_arch.group(4)
                    if whole_in:
                        in_part += float(whole_in)
                    if frac_in:
                        n, d = frac_in.split("/")
                        in_part += float(n) / float(d)
                    real_dist = ft_part + in_part / 12.0
                else:
                    try:
                        real_dist = float(val)
                    except ValueError:
                        pass

        if req.unit == "m" and real_dist is not None:
            real_dist = real_dist * 3.280839895013123

        if real_dist is None or real_dist <= 0:
            raise HTTPException(status_code=400, detail="Real world distance must be positive")

        new_ft_per_pt = round(real_dist / pixel_distance, 6)

        # 3. Locate or create target sheet entry
        target_sheet = None
        for s in data.get("sheets", []):
            if s.get("page_num") == page_num:
                target_sheet = s
                break
        if target_sheet is None:
            target_sheet = {
                "page_num": page_num,
                "sheet_label": f"Sheet_{page_num}",
                "page_type": "FLOOR_PLAN",
                "scale_string": "",
                "scale_status": "CALIBRATED",
                "ft_per_pt": new_ft_per_pt,
            }
            data.setdefault("sheets", []).append(target_sheet)
        else:
            target_sheet["ft_per_pt"] = new_ft_per_pt
            target_sheet["scale_status"] = "CALIBRATED"
            target_sheet["scale_string"] = f"Calibrated ({new_ft_per_pt:.6f} ft/pt)"

        # 4. Scale all runs belonging to this page
        for r in data.get("runs", []):
            if r.get("page_num") == page_num:
                r["ft_per_pt"] = new_ft_per_pt
                gross_pt = float(r.get("gross_length_pt", 0.0))
                if gross_pt <= 0 and "spine" in r:
                    sp = r["spine"]
                    gross_pt = math.hypot(sp["x2"] - sp["x1"], sp["y2"] - sp["y1"])
                    r["gross_length_pt"] = gross_pt
                gross_ft = round(gross_pt * new_ft_per_pt, 2)
                r["gross_length_ft"] = gross_ft
                for op in r.get("openings", []):
                    if "width_pt" in op and float(op["width_pt"]) > 0:
                        op["width_ft"] = round(float(op["width_pt"]) * new_ft_per_pt, 2)
                open_ft = round(sum(float(op.get("width_ft", 0.0)) for op in r.get("openings", [])), 2)
                r["opening_deduction_ft"] = open_ft
                r["net_length_ft"] = max(0.0, round(gross_ft - open_ft, 2))

        # 5. Dynamic Recalculation
        recalculate_run_state(run_id, data)

        return CalibrationResponse(
            success=True,
            page_num=page_num,
            measured_pixel_distance=round(pixel_distance, 4),
            new_ft_per_pt=new_ft_per_pt,
            recalculated_takeoff={
                "total_gross_lf": data["total_gross_lf"],
                "total_opening_deduction_lf": data["total_opening_deduction_lf"],
                "total_net_lf": data["total_net_lf"],
                "total_board_sf": data["total_board_sf"],
                "net_linear_footage": data["total_net_lf"],
                "net_board_footage": data["total_board_sf"],
                "total_studs_ea": data.get("total_studs_ea", 0),
                "total_track_lf": data.get("total_track_lf", 0.0),
                "by_tag": data.get("by_tag", {}),
            },
        )


@app.get("/api/blueprint/{run_id}/page/{page_num}/walls")
async def get_blueprint_page_walls(run_id: str, page_num: int):
    """Returns wall runs for a specific page with thickness and layer properties."""
    if page_num < 1:
        raise HTTPException(status_code=400, detail="Page number must be positive (>= 1)")

    with _get_run_lock(run_id):
        data = _ensure_run_loaded(run_id)
        page_walls = [r for r in data.get("runs", []) if int(r.get("page_num", 0)) == page_num]
        return {
            "run_id": run_id,
            "page_num": page_num,
            "total_walls": len(page_walls),
            "walls": page_walls,
        }


@app.post("/api/blueprint/{run_id}/page/{page_num}/walls")
async def create_manual_wall(run_id: str, page_num: int, req: WallCreateRequest):
    """Creates a new manual wall markup, calculates dimensions and deductions, updates takeoff."""
    if page_num < 1:
        raise HTTPException(status_code=400, detail="Page number must be positive (>= 1)")

    if req.height_ft is not None and float(req.height_ft) <= 0:
        raise HTTPException(status_code=400, detail="Wall height must be positive")

    with _get_run_lock(run_id):
        data = _ensure_run_loaded(run_id)

        existing_sheet_pages = {s.get("page_num") for s in data.get("sheets", []) if "page_num" in s}
        if existing_sheet_pages and page_num not in existing_sheet_pages:
            raise HTTPException(status_code=404, detail=f"Page {page_num} not found in run sheets")

        dx = req.end.x - req.start.x
        dy = req.end.y - req.start.y
        length_pt = math.hypot(dx, dy)
        if length_pt <= 0:
            raise HTTPException(status_code=400, detail="Wall start and end points must not be identical")

        if not req.tag.strip():
            raise HTTPException(status_code=400, detail="Partition tag cannot be empty")

        sheet_scale = 0.111111
        sheet_label = f"Sheet_{page_num}"
        for s in data.get("sheets", []):
            if s.get("page_num") == page_num:
                sheet_scale = float(s.get("ft_per_pt", 0.111111))
                sheet_label = s.get("sheet_label", sheet_label)
                break

        existing_ids = {r.get("run_id") for r in data.get("runs", []) if "run_id" in r}
        num = 1
        while f"RUN-M{num:02d}" in existing_ids:
            num += 1
        wall_id = f"RUN-M{num:02d}"

        gross_length_pt = length_pt
        gross_length_ft = round(gross_length_pt * sheet_scale, 2)
        openings_data = []
        opening_deduction_ft = 0.0
        if req.openings:
            for idx, op in enumerate(req.openings):
                w_ft = float(op.width_ft)
                h_ft = float(op.height_ft or 7.0)
                if w_ft <= 0:
                    raise HTTPException(status_code=400, detail="Opening width must be positive")
                if h_ft <= 0:
                    raise HTTPException(status_code=400, detail="Opening height must be positive")
                op_id = f"OP-{wall_id}-{idx+1:02d}"
                w_pt = w_ft / sheet_scale if sheet_scale > 0 else 0.0
                c_pt = {"x": op.center_pt.x, "y": op.center_pt.y} if op.center_pt else None
                new_op = {
                    "opening_id": op_id,
                    "wall_run_id": wall_id,
                    "page_num": page_num,
                    "t_start": 0.0,
                    "t_end": 0.0,
                    "width_pt": round(w_pt, 2),
                    "width_ft": w_ft,
                    "height_ft": h_ft,
                    "classification": "CONFIRMED",
                    "evidence": "MANUAL_ESTIMATOR",
                    "center_pt": c_pt,
                }
                openings_data.append(new_op)
                data.setdefault("openings", []).append(new_op)
                opening_deduction_ft += w_ft

        opening_deduction_ft = round(opening_deduction_ft, 2)
        net_length_ft = max(0.0, round(gross_length_ft - opening_deduction_ft, 2))

        wall_dict = {
            "run_id": wall_id,
            "tag": req.tag.strip(),
            "page_num": page_num,
            "sheet_label": sheet_label,
            "spine": {
                "x1": round(req.start.x, 4),
                "y1": round(req.start.y, 4),
                "x2": round(req.end.x, 4),
                "y2": round(req.end.y, 4),
                "length": round(length_pt, 4),
                "angle": round(math.degrees(math.atan2(dy, dx)), 2),
            },
            "ft_per_pt": round(sheet_scale, 6),
            "gross_length_pt": round(gross_length_pt, 4),
            "gross_length_ft": gross_length_ft,
            "opening_deduction_ft": opening_deduction_ft,
            "net_length_ft": net_length_ft,
            "openings_count": len(openings_data),
            "openings": openings_data,
            "segment_count": 1,
            "has_leader": False,
            "tag_instances": [],
            "status": "OK",
            "conflict_tags": [],
            "notes": ["Manual markup"],
            "is_manual": True,
            "height_ft": float(req.height_ft) if req.height_ft is not None else 10.0,
            "thickness_pt": None,
            "thickness_in": float(data.get("by_tag", {}).get(req.tag.strip(), {}).get("attributes", {}).get("nominal_thickness_in", 4.875)),
            "thickness_measured": False,
            "section_callout_tag": None,
            "is_height_verified": False,
            "height_source": "MANUAL_ESTIMATOR",
            "material_layers": list(data.get("by_tag", {}).get(req.tag.strip(), {}).get("attributes", {}).get("material_layers", [])),
        }

        data.setdefault("runs", []).append(wall_dict)
        recalculate_run_state(run_id, data)

        takeoff_summary = {
            "total_gross_lf": data["total_gross_lf"],
            "total_opening_deduction_lf": data["total_opening_deduction_lf"],
            "total_net_lf": data["total_net_lf"],
            "total_board_sf": data["total_board_sf"],
            "net_linear_footage": data["total_net_lf"],
            "net_board_footage": data["total_board_sf"],
            "total_studs_ea": data.get("total_studs_ea", 0),
            "total_track_lf": data.get("total_track_lf", 0.0),
            "by_tag": data.get("by_tag", {}),
        }

        return {
            "success": True,
            "wall": wall_dict,
            "recalculated_takeoff": takeoff_summary,
            "run_id": wall_id,
            "gross_length_ft": gross_length_ft,
            "net_length_ft": net_length_ft,
            "is_manual": True,
        }


@app.patch("/api/blueprint/{run_id}/walls/{wall_id}")
async def update_wall_markup(run_id: str, wall_id: str, req: WallUpdateRequest):
    """Updates endpoints, partition tag, height, or opening deductions for a wall run."""
    if req.height_ft is not None and float(req.height_ft) <= 0:
        raise HTTPException(status_code=400, detail="Wall height must be positive")

    with _get_run_lock(run_id):
        data = _ensure_run_loaded(run_id)

        target_run = None
        for r in data.get("runs", []):
            if r.get("run_id") == wall_id:
                target_run = r
                break

        if target_run is None:
            raise HTTPException(status_code=404, detail=f"Wall run '{wall_id}' not found.")

        if req.start is not None or req.end is not None:
            sp = target_run.get("spine", {})
            x1 = req.start.x if req.start is not None else float(sp.get("x1", 0.0))
            y1 = req.start.y if req.start is not None else float(sp.get("y1", 0.0))
            x2 = req.end.x if req.end is not None else float(sp.get("x2", 0.0))
            y2 = req.end.y if req.end is not None else float(sp.get("y2", 0.0))
            dx = x2 - x1
            dy = y2 - y1
            new_len_pt = math.hypot(dx, dy)
            if new_len_pt <= 0:
                raise HTTPException(status_code=400, detail="Wall start and end points must not be identical")

            target_run["spine"] = {
                "x1": round(x1, 4),
                "y1": round(y1, 4),
                "x2": round(x2, 4),
                "y2": round(y2, 4),
                "length": round(new_len_pt, 4),
                "angle": round(math.degrees(math.atan2(dy, dx)), 2),
            }
            target_run["gross_length_pt"] = round(new_len_pt, 4)
            ft_pt = float(target_run.get("ft_per_pt", 0.111111))
            target_run["gross_length_ft"] = round(new_len_pt * ft_pt, 2)

        if req.tag is not None and req.tag.strip():
            target_run["tag"] = req.tag.strip()

        if req.height_ft is not None:
            target_run["height_ft"] = float(req.height_ft)
            if req.is_height_verified is None:
                target_run["is_height_verified"] = True
                target_run["is_manual"] = True
                target_run["height_source"] = "ESTIMATOR_VERIFIED"
                if target_run.get("status") == "REVIEW":
                    target_run["status"] = "OK"

        if req.is_height_verified is not None:
            target_run["is_height_verified"] = bool(req.is_height_verified)
            if req.is_height_verified and target_run.get("status") == "REVIEW":
                target_run["status"] = "OK"
            elif not req.is_height_verified:
                target_run["status"] = "REVIEW"

        if req.status is not None:
            target_run["status"] = req.status

        if req.height_source is not None:
            target_run["height_source"] = req.height_source

        if req.thickness_in is not None:
            target_run["thickness_in"] = round(float(req.thickness_in), 3)
            if req.thickness_measured is not None:
                target_run["thickness_measured"] = bool(req.thickness_measured)

        if req.gross_length_ft is not None and req.start is None and req.end is None:
            target_run["gross_length_ft"] = round(float(req.gross_length_ft), 2)
            ded = float(target_run.get("opening_deduction_ft", 0.0))
            target_run["net_length_ft"] = max(0.0, round(target_run["gross_length_ft"] - ded, 2))

        if req.opening_deduction_ft is not None and req.openings is None:
            target_run["opening_deduction_ft"] = round(float(req.opening_deduction_ft), 2)
            grs = float(target_run.get("gross_length_ft", 0.0))
            target_run["net_length_ft"] = max(0.0, round(grs - target_run["opening_deduction_ft"], 2))

        if req.openings is not None:
            data["openings"] = [op for op in data.get("openings", []) if op.get("wall_run_id") != wall_id]
            new_openings = []
            open_ded_ft = 0.0
            p_num = int(target_run.get("page_num", 1))
            ft_pt = float(target_run.get("ft_per_pt", 0.111111))
            for idx, op in enumerate(req.openings):
                w_ft = float(op.width_ft)
                h_ft = float(op.height_ft or 7.0)
                if w_ft <= 0:
                    raise HTTPException(status_code=400, detail="Opening width must be positive")
                if h_ft <= 0:
                    raise HTTPException(status_code=400, detail="Opening height must be positive")
                op_id = f"OP-{wall_id}-{idx+1:02d}"
                w_pt = w_ft / ft_pt if ft_pt > 0 else 0.0
                c_pt = {"x": op.center_pt.x, "y": op.center_pt.y} if op.center_pt else None
                new_op = {
                    "opening_id": op_id,
                    "wall_run_id": wall_id,
                    "page_num": p_num,
                    "t_start": 0.0,
                    "t_end": 0.0,
                    "width_pt": round(w_pt, 2),
                    "width_ft": w_ft,
                    "height_ft": h_ft,
                    "classification": "CONFIRMED",
                    "evidence": "MANUAL_ESTIMATOR",
                    "center_pt": c_pt,
                }
                new_openings.append(new_op)
                data.setdefault("openings", []).append(new_op)
                open_ded_ft += w_ft

            target_run["openings"] = new_openings
            target_run["openings_count"] = len(new_openings)
            target_run["opening_deduction_ft"] = round(open_ded_ft, 2)

        target_run["net_length_ft"] = max(0.0, round(float(target_run["gross_length_ft"]) - float(target_run.get("opening_deduction_ft", 0.0)), 2))

        recalculate_run_state(run_id, data)

        takeoff_summary = {
            "total_gross_lf": data["total_gross_lf"],
            "total_opening_deduction_lf": data["total_opening_deduction_lf"],
            "total_net_lf": data["total_net_lf"],
            "total_board_sf": data["total_board_sf"],
            "net_linear_footage": data["total_net_lf"],
            "net_board_footage": data["total_board_sf"],
            "total_studs_ea": data.get("total_studs_ea", 0),
            "total_stud_lf": data.get("total_stud_lf", 0.0),
            "total_track_lf": data.get("total_track_lf", 0.0),
            "verified_height_count": data.get("verified_height_count", 0),
            "unverified_height_count": data.get("unverified_height_count", 0),
            "review_items_count": len(data.get("review_items", [])),
            "review_items": data.get("review_items", []),
            "by_tag": data.get("by_tag", {}),
        }

        return {
            "success": True,
            "wall": target_run,
            "recalculated_takeoff": takeoff_summary,
            "run_id": wall_id,
            "gross_length_ft": target_run["gross_length_ft"],
            "net_length_ft": target_run["net_length_ft"],
            "is_manual": bool(target_run.get("is_manual", False)),
        }


@app.post("/api/runs/update")
async def post_runs_update(req: RunUpdateRequest):
    """POST endpoint alias for updating a wall run matching requirement contract."""
    return await update_wall_markup(run_id=req.run_id, wall_id=req.wall_id, req=req)


@app.post("/api/blueprint/{run_id}/walls/{wall_id}")
async def post_wall_markup(run_id: str, wall_id: str, req: WallUpdateRequest):
    """POST alias for PATCH /api/blueprint/{run_id}/walls/{wall_id}."""
    return await update_wall_markup(run_id=run_id, wall_id=wall_id, req=req)


@app.delete("/api/blueprint/{run_id}/walls/{wall_id}", response_model=WallDeleteResponse)
async def delete_wall_markup(run_id: str, wall_id: str):
    """Deletes a wall markup and recomputes project takeoff totals."""
    with _get_run_lock(run_id):
        data = _ensure_run_loaded(run_id)

        target_run = None
        for r in data.get("runs", []):
            if r.get("run_id") == wall_id:
                target_run = r
                break

        if target_run is None:
            raise HTTPException(status_code=404, detail=f"Wall run '{wall_id}' not found.")

        data["runs"] = [r for r in data.get("runs", []) if r.get("run_id") != wall_id]
        data["openings"] = [op for op in data.get("openings", []) if op.get("wall_run_id") != wall_id]

        recalculate_run_state(run_id, data)

        return WallDeleteResponse(
            success=True,
            deleted_id=wall_id,
            recalculated_takeoff={
                "total_gross_lf": data["total_gross_lf"],
                "total_opening_deduction_lf": data["total_opening_deduction_lf"],
                "total_net_lf": data["total_net_lf"],
                "total_board_sf": data["total_board_sf"],
                "net_linear_footage": data["total_net_lf"],
                "net_board_footage": data["total_board_sf"],
                "total_studs_ea": data.get("total_studs_ea", 0),
                "total_track_lf": data.get("total_track_lf", 0.0),
                "by_tag": data.get("by_tag", {}),
            },
        )


# =============================================================================
# CONVENIENCE FIXTURE & SAMPLE ENDPOINTS
# =============================================================================


@app.get("/api/fixtures")
async def list_available_fixtures():
    """Lists synthetic blueprint fixtures available for instantaneous 1-click takeoff."""
    catalog = [
        {
            "fixture_id": "fixture_wall20.pdf",
            "name": "fixture_wall20.pdf",
            "title": "20ft Partition Wall (Worked Example 8.7.1)",
            "description": "20.00 LF partition with scale 1/8\" = 1'-0\" and Tag 7A",
            "tags": ["7A"],
        },
        {
            "fixture_id": "fixture_door.pdf",
            "name": "fixture_door.pdf",
            "title": "20ft Partition with 3ft Door Opening",
            "description": "Standard 20ft run with 3ft door deduction and Tag 1A",
            "tags": ["1A"],
        },
        {
            "fixture_id": "fixture_lumber.pdf",
            "name": "fixture_lumber.pdf",
            "title": "Floor Plan with Framing Lumber Tags (2X4, 2X6)",
            "description": "Demonstrates negative lookahead exclusion of lumber dimensions",
            "tags": ["1A", "2X4", "2X6"],
        },
        {
            "fixture_id": "fixture_multiwall.pdf",
            "name": "fixture_multiwall.pdf",
            "title": "Multi-Wall Floor Plan with T-Junctions",
            "description": "Complex floor plan with multiple intersecting partition types",
            "tags": ["1A", "2B"],
        },
    ]
    return {"fixtures": catalog}


@app.post("/api/fixture/run/{fixture_name}", status_code=202)
async def run_fixture_pipeline(fixture_name: str):
    """Triggers pipeline execution directly against a fixture blueprint."""
    fixture_path = FIXTURES_DIR / fixture_name
    if not fixture_path.exists():
        fixture_path = FIXTURES_DIR / f"{fixture_name}.pdf"
    if not fixture_path.exists():
        raise HTTPException(status_code=404, detail=f"Fixture '{fixture_name}' not found.")

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    run_id = f"run_{timestamp_str}_{short_id}"

    RUNS[run_id] = {
        "run_id": run_id,
        "file_id": fixture_name,
        "pdf_path": str(fixture_path),
        "status": "processing",
        "progress_pct": 0,
        "stage": "S00: Initializing",
        "message": f"Running fixture {fixture_name}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "events": [],
        "error": None,
    }

    t = threading.Thread(
        target=_run_pipeline_worker,
        args=(run_id, str(fixture_path), {}),
        daemon=True,
    )
    t.start()

    return {
        "run_id": run_id,
        "file_id": fixture_name,
        "status": "processing",
        "message": f"Pipeline processing started for {fixture_name}.",
    }


# =============================================================================
# STATIC SPA FRONTEND SERVING
# =============================================================================


@app.get("/")
async def serve_root_spa():
    """Serves the unified CAD Workbench Single Page Application (SPA)."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return HTMLResponse(
        "<!DOCTYPE html><html><head><title>PDF ENGINE</title></head>"
        "<body style='background:#070b13;color:#dde2f8;font-family:sans-serif;padding:2rem;'>"
        "<h1>PDF ENGINE Workbench Backend</h1>"
        "<p>FastAPI API is operational. Static SPA assets loading...</p>"
        "</body></html>"
    )


# Mount static assets directory
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)

# Project: Drywall Estimator Production Workbench

## Architecture
The Drywall Estimator Workbench is a production web application and automated pipeline built on FastAPI (backend), PyMuPDF vector CAD analysis, Jev AI / type-safe assembly classification, and a responsive SVG/HTML5 canvas viewer (frontend).
- **Backend Architecture (`qto/`, `app.py`)**:
  - `qto/sheet_index.py`: Full-document sheet indexer classifying 71 pages into `FLOOR_PLAN`, `PARTITION_SCHEDULE`, `CEILING_PLAN`, `LEGEND`, `OTHER`.
  - `qto/assemblies.py` & S03: Assembly material extraction from schedule sheets (A-900, A-901, A-801, A-802, A-706), rotated text span grouping, and structured layer stack parsing (`material_layers`).
  - `qto/classify/jev.py` & `qto/classify/mock.py`: Jev LLM / TypeSafe / cached registry drywall assembly classification with probability threshold $\ge 0.85$.
  - `qto/tags.py`: Partition schedule tag mining with lumber lookahead exclusion, and spatial floor plan tag discovery.
  - `qto/trace_walls.py` & `qto/dedup.py`: Double-line parallel casing pairing, physical wall thickness measurement (`thickness_in`), collinear chaining, and deduplication into `WallRun`.
  - `qto/section_heights.py` (New): Spatial section callout tag detection (`A-706/09`, `A-801`, `A-702/01`), referenced section detail sheet navigation, explicit ceiling/wall height extraction, and 10 ft fallback with estimator review flagging (`is_height_verified=False`, `status="REVIEW"`).
  - `qto/quantities.py` & `qto/takeoff.py`: Gross/net LF, opening deductions, board SF, stud count, runner tracks, and review item aggregation.
  - `qto/annotate.py`: PyMuPDF dual-red vector drawing annotations (8.0pt bright red highlight band + 2.2pt dark red CAD edge spine) and interactive callouts.
  - `qto/export.py`: 7-sheet openpyxl Excel serialization with live uppercase formulas, thickness, and height verification metadata.
  - `app.py`: FastAPI application serving REST endpoints, SSE progress, sheet catalogs, calibration, and markup CRUD.
- **Frontend Architecture (`static/`)**:
  - `static/index.html`: Estimator workbench UI (Header, Left Navigation/Sheet Drawer, Vector Canvas Viewer, Right Wall Inspector, Bottom Takeoff Schedule Dock).
  - `static/js/viewer.js`: Pan/zoom, SVG overlays, dual-red highlights, 2-point calibration tool, manual wall ruler, draggable endpoint handles.
  - `static/js/app.js`: State management, sheet selector, tool mode manager, dynamic takeoff recalculation, unverified height review badges.
  - `static/css/workbench.css`: Responsive CAD dark theme, collision-free header down to 1024px.
- **Automated Test Suite (`tests/`)**:
  - Unit tests, regression tests, API contract tests, mathematical ground truth assertions, and real blueprint E2E tests (`uploads/doc_20261104_101950_6cbd34.pdf`).

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Schedule Sheet Parsing & Extraction | Parse partition schedule sheets (A-900, A-901, A-801, A-802, A-706) in S03 passing `schedule_page_indices`, extracting material specs and layer structures | M1 | R1, Survey |
| F2 | Structured Layer Stack Modeling | Construct explicit `material_layers` breakdown (face finish, core studs, back finish, fire ratings) in `qto/assemblies.py` | M1 | R1, Survey |
| F3 | Jev Drywall Classification ($\ge 0.85$) | Update Jev classification filter threshold from 0.90 to $\ge 0.85$ across `qto/classify/jev.py`, `pipeline.py`, and `test.py` | M1 | R2, Survey |
| F4 | Clean Registry Cache | Purge poisoned entries from `drywall_registry.json` so all 19 drywall partition tags qualify with prob $\ge 0.85$ while glass/privacy walls are rejected | M1 | R2, Survey |
| F5 | Wall Thickness Measurement | Calculate and persist `thickness_in` from `twin_offsets * ft_per_pt * 12.0` in `WallRun` and `WallRun.to_dict()`, with schedule nominal fallback | M2 | R3, Survey |
| F6 | Floor Plan Tag & Geometry Matching | Match qualified drywall tags to vector linework on floor plans via leader line endpoints and collinear chaining | M2 | R3, Survey |
| F7 | Visual Markup & Highlighting | Render dual-red vector highlight bands (8.0pt bright red) and crisp edge spines (2.2pt dark red) in PDF and canvas viewer | M2 | R3, Survey |
| F8 | Section Callout Tag Discovery | Detect circular section/detail callouts (`A-706/09`, `A-801`, `A-702/01`, `A-802/4`, `A-907/2`) near floor plan wall runs within 120 pt radius | M3 | R4, Survey |
| F9 | Section Detail Sheet Height Lookup | Navigate to referenced section detail sheet (e.g. A-706 Page 52, A-702 Page 48) and parse explicit ceiling/wall height dimensions | M3 | R4, Survey |
| F10 | Standard 10 ft Height Fallback & Review Flag | If section callout or explicit height is missing, fall back to 10.0 ft height, set `is_height_verified=False`, `status="REVIEW"`, and append review item | M3 | R4, Survey |
| F11 | Verified Takeoff Schedule Backend Serialization | Serialize `thickness_in`, `thickness_measured`, `is_height_verified`, `height_source`, `section_callout_tag`, and `material_layers` in REST APIs and Excel | M4 | R5, Survey |
| F12 | Takeoff Schedule Dock UI Enhancements | Add `Thickness` and `Height Verification` status columns to bottom dock table with interactive filtering for unverified review runs | M4 | R5, Survey |
| F13 | Wall Inspector Panel Updates | Display measured wall thickness, layer breakdown, section callout reference, and verified/unverified height badge in UI inspector | M4 | R5, Survey |
| F14 | Live Recalculations on Markup Edits | Dynamically update gross/net LF, SF, and review items when markups or opening deductions are modified in UI or API | M4 | R5, Survey |
| F15 | Windows Automated Test Suite Pass | Ensure 100% of automated tests in `tests/` pass cleanly on Windows without failures or xfails | M5 | R5, Acceptance Criteria |
| F16 | End-to-End Test Blueprint Validation | Validate full automated workflow against `uploads/doc_20261104_101950_6cbd34.pdf` verifying R1-R5 acceptance criteria | M5 | R5, Acceptance Criteria |
| F17 | Zero-Git Constraint & Forensic Integrity Audit | Execute zero git commands and verify complete absence of hardcoding, facades, or integrity violations via Forensic Auditor | M5 | Acceptance Criteria, Audit |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Schedule Sheet Parsing & Jev Classification Engine (R1, R2) | Fix S03 `schedule_page_indices`, rotated text grouping, structured layers, Jev threshold $\ge 0.85$, and clean registry cache | none | DONE |
| M2 | Floor Plan Geometry, Thickness Measurement & Visual Annotation (R3) | Compute and store `thickness_in` from double-line casing, floor plan tag matching, dual-red visual highlighting | M1 | DONE |
| M3 | Section Tag Callout & Height Verification Engine (R4) | Section callout discovery on floor plans, referenced detail sheet navigation, explicit height lookup, 10 ft fallback and review flagging | M2 | IN_PROGRESS |
| M4 | Takeoff Schedule Dock, UI Inspector & Workbench Integration (R3, R4, R5) | REST API serialization, UI table columns for thickness & verification status, inspector details, live recalculation | M3 | PLANNED |
| M5 | E2E Test Suite Pass, Platform Execution & Hardening (R5) | Full test suite pass on Windows, end-to-end blueprint validation, zero git commands, Forensic Integrity Audit | M4 | PLANNED |

---

## Interface Contracts

### 1. Partition Assembly & Layer Structure Contract (M1 ↔ M2, M4)
- **Data Structure (`qto/assemblies.py`)**:
  ```python
  @dataclass
  class WallAssembly:
    tag: str
    materials_raw: str
    probability: float
    decision: str  # "DRYWALL" or "NOT_DRYWALL"
    stud_depth_in: float  # e.g. 2.5, 3.625, 6.0
    stud_spacing_in: float  # e.g. 16.0, 24.0
    stud_gauge: str  # e.g. "25 GA", "20 GA"
    board_type: str  # e.g. "5/8\" TYPE X GWB"
    board_thickness_in: float  # 0.625
    layers_per_face: int  # 1 or 2
    finished_faces: int  # 1 or 2
    fire_rated: bool  # True if 1-HR, 2-HR
    nominal_thickness_in: (
        float  # stud_depth_in + finished_faces * layers_per_face *
               # board_thickness_in
    )
    material_layers: List[Dict[str, str]]
    # Example:
    # [
    #   {"side": "Face A", "layer": "1", "material": "5/8\" Type X Gypsum Wall Board"},
    #   {"side": "Core", "layer": "Framing", "material": "6\" 25 GA Metal Studs @ 16\" O.C."},
    #   {"side": "Core", "layer": "Insulation", "material": "Sound Attenuation Blanket"},
    #   {"side": "Face B", "layer": "1", "material": "5/8\" Type X Gypsum Wall Board"}
    # ]
```

### 2. WallRun Geometry & Thickness Contract (M2 ↔ M3, M4)
- **Data Structure (`qto/dedup.py`)**:
  ```python
  @dataclass
  class WallRun:
    run_id: str
    tag: str
    page_num: int
    sheet_label: str
    spine: Tuple[Tuple[float, float], Tuple[float, float]]
    gross_length_pt: float
    gross_length_ft: float
    opening_deduction_ft: float
    net_length_ft: float
    openings: List[Any]
    segments: List[Any]
    status: str  # "VERIFIED" or "REVIEW"
    ft_per_pt: float
    is_manual: bool
    height_ft: float  # default 10.0 or verified section height
    thickness_pt: Optional[float] = None
    thickness_in: Optional[float] = None  # measured or nominal
    thickness_measured: bool = False  # True if from double-line linework
    section_callout_tag: Optional[str] = (
        None  # e.g. "A-706 / 09", "A-801", "A-702 / 01"
    )
    is_height_verified: bool = False  # True if explicit section height found
    height_source: str = "UNVERIFIED_HEIGHT_DEFAULT"  # or detail reference
    material_layers: List[Dict[str, str]] = field(default_factory=list)
```

### 3. Section Callout & Height Verification Contract (M3 ↔ M4)
- **Module Interface (`qto/section_heights.py`)**:
  ```python
  def verify_wall_run_heights(
      doc: fitz.Document, wall_runs: List[WallRun], sheet_catalog: List[Dict]
  ) -> Tuple[List[WallRun], List[Dict[str, Any]]]:
    """Spatially matches wall runs on floor plans to nearest section callout tags

    (within 120 pt radius), navigates to referenced section detail sheet,
    extracts explicit ceiling/wall height, or falls back to 10.0 ft default with
    is_height_verified=False and review flagging.

    Returns:
        (updated_wall_runs, review_items)
    """
```

### 4. REST Takeoff API Contract (M4 ↔ Frontend)
- **Endpoint**: `GET /api/takeoff/{run_id}`
- **Response Format**:
  ```json
  {
    "run_id": "RUN-20261104-xxxx",
    "summary": {
      "total_gross_lf": 842.50,
      "total_net_lf": 795.00,
      "total_board_sf": 6360.00,
      "total_walls": 19,
      "verified_height_count": 14,
      "unverified_height_count": 5
    },
    "walls": [
      {
        "run_id": "RUN-001",
        "tag": "7A",
        "sheet_label": "A-101",
        "page_num": 15,
        "gross_length_ft": 112.71,
        "net_length_ft": 112.71,
        "thickness_in": 4.88,
        "thickness_measured": true,
        "height_ft": 8.0,
        "is_height_verified": true,
        "height_source": "A-706 Detail 09",
        "section_callout_tag": "A-706 / 09",
        "status": "VERIFIED",
        "material_layers": [
          {"side": "Face A", "material": "5/8\" Type X GWB"},
          {"side": "Core", "material": "2-1/2\" 25 GA Metal Studs @ 16\" O.C."}
        ]
      },
      {
        "run_id": "RUN-017",
        "tag": "5E",
        "sheet_label": "A-101",
        "page_num": 15,
        "gross_length_ft": 8.32,
        "net_length_ft": 8.32,
        "thickness_in": 8.50,
        "thickness_measured": true,
        "height_ft": 10.0,
        "is_height_verified": false,
        "height_source": "UNVERIFIED_HEIGHT_DEFAULT",
        "section_callout_tag": null,
        "status": "REVIEW",
        "material_layers": [...]
      }
    ],
    "review_items": [
      {
        "run_id": "RUN-017",
        "issue": "Unverified wall height: No section callout found on floor plan. Using standard 10.0 ft fallback.",
        "action_required": "Estimator review required to confirm wall height against architectural elevations."
      }
    ]
  }
  ```

---

## Code Layout
- Backend Implementation:
  - `qto/sheet_index.py`: Full-document sheet indexer and classifier.
  - `qto/assemblies.py`: S03 assembly text extractor and layer stack generator.
  - `qto/classify/jev.py`: Jev classifier with threshold $\ge 0.85$.
  - `qto/tags.py`: S02 schedule tag discovery and S08 floor plan tag discovery.
  - `qto/trace_walls.py`: S09-S12 linework tracing and casing thickness detection.
  - `qto/dedup.py`: S13 deduplication, centerline spine, and `WallRun` construction.
  - `qto/section_heights.py`: S13B section callout tag discovery & height verification engine.
  - `qto/quantities.py`: S14 takeoff mathematical calculations and review item assembly.
  - `qto/annotate.py`: S15 dual-red vector drawing annotations.
  - `qto/export.py`: S16 7-sheet openpyxl Excel serialization.
  - `qto/pipeline.py`: 16-stage pipeline orchestrator.
  - `app.py`: FastAPI application server and REST endpoints.
- Frontend Implementation:
  - `static/index.html`: Estimator workbench DOM layout.
  - `static/css/workbench.css`: Responsive CSS and status badge styles.
  - `static/js/viewer.js`: Canvas viewer, pan/zoom, SVG overlays.
  - `static/js/app.js`: State management, takeoff dock rendering, review filter.
- Tests & Verification:
  - `tests/`: Automated pytest suites.
  - `tests/test_drywall_workflow_e2e.py`: Dedicated R1-R5 verification suite.

# Test Infrastructure Specification: Drywall Estimator Production Workbench

**Document Version**: 2.1.0  
**Status**: APPROVED & ACTIVE  
**Scope**: Full End-to-End Test Suites for Estimator Production Workbench (`tests/test_e2e_workbench.py`) and Drywall Takeoff Workflow R1–R5 (`tests/test_drywall_workflow_e2e.py`)  
**Target Environment**: Windows 11 / Server x64, Python 3.13.7, PyMuPDF 2.0, openpyxl 3.1.5, FastAPI 0.162.0, pytest 9.2.0  

---

## 1. Test Philosophy & Core Methodology

The Drywall Estimator Production Workbench test infrastructure enforces an opaque-box, requirement-driven testing standard derived directly from `PROJECT.md`, `ORIGINAL_REQUEST.md`, and `Drywall_QTO_SOP.docx`.

### Core Tenets
1. **Opaque-Box Requirement Derivation**: All test cases originate from documented functional specifications and interface contracts in `PROJECT.md § Feature Inventory` (F1–F17) and `PROJECT.md § Interface Contracts`. Tests treat backend endpoints and UI assets through external interfaces without relying on internal private state.
2. **Deterministic Offline Verification**: Mandated by SOP Sections 8.11 and 9.2, all unit, regression, and mathematical tests operate without external network dependencies. Deterministic synthetic blueprints (`tests/fixtures/`) provide mathematically exact CAD geometries, while real blueprints (`uploads/doc_20261104_101950_6cbd34.pdf`) validate real-world floor plan vector parsing.
3. **Mathematical Parity Ground Truth**: Numerical calculations adhere strictly to authoritative derivations:
   - SOP Section 8.7.1 worked example ($L_{\text{gross}} = 20.00\text{ LF}$, $L_{\text{net}} = 17.00\text{ LF}$, $A_{\text{board}} = 358.00\text{ SF}$, 16 studs, $37.00\text{ LF}$ metal track, $57.00\text{ LF}$ wood plates).
   - 2-point scale calibration formula ($d_{\text{pt}} = \sqrt{(x_2 - x_1)^2 + (y_2 - y_1)^2}$, $\text{ft\_per\_pt} = \text{distance\_ft} / d_{\text{pt}}$).
4. **4-Tier Requirement-Driven Test Pyramid**:
   - **Tier 1: Feature Coverage**: Explicit test coverage for each of the 17 features (F1 through F17).
   - **Tier 2: Boundary & Corner Cases**: Out-of-bounds page requests, zero/negative dimensions, 71-page blueprint navigation stress, empty markups, and invalid calibration inputs.
   - **Tier 3: Cross-Feature Combinations**: Multi-step workflows combining sheet selection, wall detection, scale calibration, manual markup creation, opening deductions, and schedule synchronization.
   - **Tier 4: Real-World Blueprint Scenario**: End-to-end execution against `uploads/doc_20261104_101950_6cbd34.pdf` targeting Sheet A-101 (Page 15) verifying non-zero gross LF, net LF, dual-red visual annotations, and takeoff schedule generation.
5. **Progressive Testability & Zero-Facade Integrity**:
   - Tests assert real calculations and verifiable outputs. No mock facades that pass without exercising logic.
   - For downstream milestone contracts (M1–M5), tests cleanly adapt to interface readiness while maintaining complete specification assertions.

---

## 2. Feature Inventory & Test Coverage Mapping (F1–F17)

| Feature ID | Feature Name | Milestone | Tier 1 (Unit/Contract) | Tier 2 (Boundary) | Tier 3 (Cross-Feature) | Tier 4 (Real-World) |
|:----------:|:-------------|:---------:|:----------------------:|:-----------------:|:----------------------:|:-------------------:|
| **F1** | Blueprint Sheet Indexing Fix | M1 | `test_f1_sheet_indexing_classification` | `test_tier2_boundary_71_page_indexing` | `test_tier3_combined_workflow` | `test_tier4_real_world_blueprint_sheet_a101` |
| **F2** | Real Blueprint Wall Detection | M1 | `test_f2_real_blueprint_wall_detection` | `test_tier2_empty_page_wall_detection` | `test_tier3_combined_workflow` | `test_tier4_real_world_blueprint_sheet_a101` |
| **F3** | Selective Sheet Processing | M1 | `test_f3_selective_sheet_processing_contract` | `test_tier2_selective_processing_invalid_pages` | `test_tier3_combined_workflow` | `test_tier4_real_world_blueprint_sheet_a101` |
| **F4** | Out-of-bounds Contract Fix | M1 | `test_f4_out_of_bounds_page_contract` | `test_tier2_boundary_out_of_bounds_pages` | — | — |
| **F5** | 2-Point Scale Calibration API | M2 | `test_f5_twopoint_calibration_math_and_api` | `test_tier2_invalid_calibration_inputs` | `test_tier3_combined_workflow` | `test_tier4_real_world_blueprint_sheet_a101` |
| **F6** | Manual Wall Markup CRUD APIs | M2 | `test_f6_manual_wall_crud_operations` | `test_tier2_empty_and_zero_wall_markups` | `test_tier3_combined_workflow` | `test_tier4_real_world_blueprint_sheet_a101` |
| **F7** | Takeoff Recalculation API | M2 | `test_f7_takeoff_recalculation_engine` | `test_tier2_excessive_opening_deduction` | `test_tier3_combined_workflow` | `test_tier4_real_world_blueprint_sheet_a101` |
| **F8** | UI Layout Streamlining | M3 | `test_f8_ui_layout_streamlining_clean_dom` | `test_tier2_ui_dom_elements_presence` | — | — |
| **F9** | Header Collision & Responsive Fix | M3 | `test_f9_header_responsive_layout` | `test_tier2_responsive_viewport_media_queries` | — | — |
| **F10** | Multi-Page Sheet Navigation | M3 | `test_f10_multipage_sheet_navigation_catalog` | `test_tier2_boundary_71_page_indexing` | `test_tier3_combined_workflow` | `test_tier4_real_world_blueprint_sheet_a101` |
| **F11** | 2-Point Scale Canvas Tool | M4 | `test_f11_canvas_calibration_tool_definitions` | `test_tier2_invalid_calibration_inputs` | `test_tier3_combined_workflow` | — |
| **F12** | Manual Wall Ruler Tool | M4 | `test_f12_manual_wall_ruler_tool_definitions` | `test_tier2_zero_length_manual_wall` | `test_tier3_combined_workflow` | — |
| **F13** | Interactive Markup Editing | M4 | `test_f13_markup_editing_event_handlers` | `test_tier2_empty_and_zero_wall_markups` | `test_tier3_combined_workflow` | — |
| **F14** | Dual-Red Visual Annotations | M4 | `test_f14_dual_red_vector_annotation_structure`| `test_tier2_annotation_empty_runs` | `test_tier3_combined_workflow` | `test_tier4_real_world_blueprint_sheet_a101` |
| **F15** | Takeoff Schedule Dock | M4 | `test_f15_takeoff_schedule_dock_table` | `test_tier2_empty_schedule_state` | `test_tier3_combined_workflow` | `test_tier4_real_world_blueprint_sheet_a101` |
| **F16** | Windows Test Verification | M5 | `test_f16_windows_environment_compatibility` | `test_tier2_windows_file_locking_immunity` | — | — |
| **F17** | End-to-End Real Blueprint Validation | M5 | `test_f17_e2e_real_blueprint_complete_run` | `test_tier2_boundary_71_page_indexing` | `test_tier3_combined_workflow` | `test_tier4_real_world_blueprint_sheet_a101` |

---

## 3. Test Tier Specifications

### Tier 1: Feature Coverage (F1–F17)
- **F1 (Sheet Indexing)**: Verify S01 indexes all sheets, parses title blocks, extracts sheet numbers (`A-100`, `A-101`), and correctly classifies construction floor plans as `FLOOR_PLAN` instead of false-positive `PARTITION_SCHEDULE`.
- **F2 (Wall Detection)**: Run wall linework extraction and wall segment tracing on floor plan sheets. Verify detected wall count $> 0$, gross linear footage $> 0$, and net linear footage $> 0$.
- **F3 (Selective Processing)**: Issue `POST /api/process/{file_id}` with `config={"selected_pages": [15], "run_mode": "floor_plans_only"}`. Verify backend honors selective page filtering and processes only requested sheets.
- **F4 (Out-of-bounds Contract Fix)**: Query `GET /api/blueprint/{run_id}/page/{page_num}/image` for $page\_num \le 0$ or $page\_num > \text{page\_count}$. Verify HTTP 404 response with clean JSON detail (no 500 "document closed" PyMuPDF lifecycle crash).
- **F5 (2-Point Scale Calibration)**: Calculate scale calibration factor $ft\_per\_pt = \text{distance\_ft} / \sqrt{(x_2 - x_1)^2 + (y_2 - y_1)^2}$. Verify takeoff values scale quadratically for board SF and linearly for LF. Test `POST /api/blueprint/{run_id}/page/{page_num}/calibrate` contract.
- **F6 (Manual Wall CRUD)**: Test `WallRun` object creation with `is_manual: true`, coordinate updates, partition tag change, opening deduction addition, and deletion.
- **F7 (Takeoff Recalculation)**: Verify dynamic recalculation of gross LF, net LF, board SF, studs, and tracks upon adding or modifying manual markups or opening deductions.
- **F8 (UI Streamlining)**: Verify `static/index.html` has eliminated dead buttons ("Reconciliation", "Quality Control"), cosmetic layer checkboxes, and redundant warning banners.
- **F9 (Header Collision & Responsiveness)**: Verify `static/css/workbench.css` contains responsive rules avoiding fixed-width header truncation on viewports $<1440\text{px}$.
- **F10 (Multi-Page Sheet Navigation)**: Verify sheet catalog generation for 70+ page blueprints containing `page_num`, `sheet_label`, `sheet_title`, `page_type`, `scale`, and `ft_per_pt`.
- **F11 (Canvas Calibration Tool)**: Inspect `static/js/viewer.js` and `static/js/app.js` for 2-point calibration tool registration, pointer click capture, and modal dispatch.
- **F12 (Manual Wall Ruler Tool)**: Inspect `static/js/viewer.js` and `static/js/app.js` for ruler and manual wall drawing modes, mouse/pointer drag tracking, and SVG preview rendering.
- **F13 (Interactive Markup Editing)**: Inspect `static/js/viewer.js` for markup selection, draggable endpoint handles, tag/height update hooks, and deletion controls.
- **F14 (Dual-Red Annotations)**: Verify `qto/annotate.py` and output PDF drawing structures generate 8.0pt bright red highlight bands ($RGB=(1, 0, 0)$, alpha 0.32) and 2.2pt dark red centerline spines ($RGB=(0.8, 0, 0)$, alpha 0.90).
- **F15 (Takeoff Schedule Dock)**: Verify `static/index.html` and `static/js/app.js` render a responsive takeoff schedule table displaying Tag, Length, Height, Openings, Net LF, and SF.
- **F16 (Windows Compatibility)**: Verify all file system interactions use `pathlib.Path` or `os.path.join`, operate cleanly on Windows without file locking (`PermissionError`), and pass 100% on Windows.
- **F17 (Real Blueprint E2E Validation)**: Execute full pipeline workflow on `uploads/doc_20261104_101950_6cbd34.pdf` targeting Sheet A-101 (Page 15) and assert non-zero takeoff metrics.

### Tier 2: Boundary & Corner Cases
- **B1: Out-of-bounds Page Requests**: Request page 0, page -1, page 72, and page 999 against a 71-page document. Assert HTTP 404 with clean message.
- **B2: Zero and Negative Dimensions**:
  - Wall segment where $(x_1, y_1) == (x_2, y_2)$: length $= 0\text{ pt}$. Verify handled cleanly without `ZeroDivisionError`.
  - Negative wall height ($-10.0\text{ ft}$) or zero height ($0.0\text{ ft}$): verify validation error or clamped behavior.
  - Opening deduction width $>$ gross wall length ($25.0\text{ ft}$ opening on $20.0\text{ ft}$ wall): net LF clamped to $0.00\text{ LF}$ (never negative).
- **B3: 71-Page Large Blueprint Navigation**:
  - Test indexing 71 pages of `uploads/doc_20261104_101950_6cbd34.pdf`.
  - Verify boundary pages: Page 1 (Title), Page 15 (A-101), Page 71 (Final).
  - Verify zero memory leak and prompt file handle closure.
- **B4: Empty and Missing Markups**:
  - Takeoff calculation with 0 wall runs: returns exactly $0.00\text{ LF}$ gross, $0.00\text{ LF}$ net, $0.00\text{ SF}$ board, 0 studs.
  - Deleting the last remaining wall markup restores empty takeoff schedule state cleanly.
- **B5: Invalid Calibration Inputs**:
  - Identical points $pt_1 == pt_2$ ($d_{\text{pt}} = 0$): reject with descriptive validation error (no division by zero).
  - Negative real-world distance ($-15.0\text{ ft}$): reject with validation error.
  - Zero real-world distance ($0.0\text{ ft}$): reject with validation error.

### Tier 3: Cross-Feature Combinations
- Multi-step workflow test exercising the complete estimator journey:
  1. **Step 1: Sheet Selection**: Ingest `uploads/doc_20261104_101950_6cbd34.pdf` and select Sheet A-101 (Page 15).
  2. **Step 2: Wall Detection**: Extract CAD linework (5,951 segments, 220 door arcs) and trace walls.
  3. **Step 3: Interactive 2-Point Calibration**: Apply custom 2-point scale ($240.0\text{ pt} = 20.0\text{ ft} \implies ft\_per\_pt = 0.083333$) updating sheet scale.
  4. **Step 4: Manual Wall Run Creation**: User draws manual wall run ($180.0\text{ pt}$, tag "5E", height $12.0\text{ ft}$). Gross length $= 180.0 \times 0.083333 = 15.00\text{ LF}$.
  5. **Step 5: Opening Deduction Addition**: Estimator adds a $3.0\text{ ft} \times 7.0\text{ ft}$ door opening to the manual wall run. Net length $= 12.00\text{ LF}$.
  6. **Step 6: Schedule Sync & Recalculation**: Takeoff schedule dynamically updates:
     $$\Delta L_{\text{gross}} = +15.00\text{ LF}, \quad \Delta L_{\text{net}} = +12.00\text{ LF}$$
     $$\Delta A_{\text{board}} = (15.00 \times 12.00 - 3.00 \times 7.00) \times 2 = (180.00 - 21.00) \times 2 = 318.00\text{ SF}$$

### Tier 4: Real-World Blueprint Scenario
- **Dataset**: MTA Blueprint Set `uploads/doc_20261104_101950_6cbd34.pdf` (29.1 MB, 71 pages).
- **Target Sheet**: Sheet **A-101** — Page 15 (First Floor Construction Plan).
- **Authoritative Oracles & Derived Ground Truth**:
  - Page Dimensions: $2592.0 \times 1728.0\text{ pt}$ (ARCH D at 72 dpi).
  - Detected Architectural Scale: `1/8" = 1'-0"` $\implies ft\_per\_pt = 0.111111$.
  - CAD Linework: $5,951$ straight vector segments, $220$ door swing arcs.
  - Tag Callout Instances: $31$ instances located on Page 15.
  - Raw Wall Runs Traced: $27$ runs.
  - Consolidated Wall Runs (Deduplicated): $19$ runs.
  - Quantitative Totals:
    - Total Gross Linear Footage: $495.83\text{ LF} \pm 2.00\text{ LF}$.
    - Total Opening Deductions: $22.62\text{ LF} \pm 1.00\text{ LF}$.
    - Total Net Linear Footage: $473.21\text{ LF} \pm 2.00\text{ LF}$.
    - Total Board Surface Area: $>9,000.00\text{ SF}$.
  - Annotation Output: Verified PyMuPDF vector drawing paths containing dual-red stroke geometry ($RGB=(1,0,0)$ highlight band and $RGB=(0.8,0,0)$ spine edge).

---

## 4. Test Infrastructure Architecture & Directory Layout

```
tests/
├── fixtures/                           # Deterministic synthetic CAD blueprints
│   ├── fixture_wall20.pdf              # 20ft wall, 1/8" scale, Tag 7A
│   ├── fixture_door.pdf                # 20ft wall, 3ft door deduction, Tag 1A
│   ├── fixture_lumber.pdf              # 2X4, 2X6 negative lookahead exclusion
│   ├── fixture_scale.pdf               # Multi-scale catalog and scale bar
│   └── fixture_multiwall.pdf           # T-junctions and intersecting partitions
├── make_fixtures.py                    # Programmatic PyMuPDF vector generator
├── test_fixtures.py                    # Fixture geometry and text verification
├── test_quantities.py                  # SOP 8.7.1 mathematical parity verification
├── test_pipeline.py                    # S00-S16 pipeline stage integration
├── test_export.py                      # 7-sheet openpyxl Excel verification
├── test_api.py                         # REST endpoint unit tests
├── test_challenger_verification.py     # Adversarial stress tests & file lock checks
├── test_e2e_workbench.py              # 4-TIER E2E WORKBENCH TEST SUITE (F1–F17)
└── test_drywall_workflow_e2e.py       # 4-TIER DRYWALL WORKFLOW TEST SUITE (R1–R5)
```

---

## 5. Test Execution Protocol

### Test Runner Commands
```powershell
# 1. Run Drywall Workflow E2E Test Suite (Requirements R1–R5)
python -m pytest -v tests/test_drywall_workflow_e2e.py

# 2. Run targeted test tiers in Drywall Workflow suite
python -m pytest -v tests/test_drywall_workflow_e2e.py -k "tier1"
python -m pytest -v tests/test_drywall_workflow_e2e.py -k "tier2"
python -m pytest -v tests/test_drywall_workflow_e2e.py -k "tier3"
python -m pytest -v tests/test_drywall_workflow_e2e.py -k "tier4"

# 3. Run complete E2E Workbench Test Suite
python -m pytest -v tests/test_e2e_workbench.py

# 4. Run both E2E test suites together (63 tests)
python -m pytest -v tests/test_drywall_workflow_e2e.py tests/test_e2e_workbench.py

# 5. Run entire project regression test suite
python -m pytest -v tests/
```

### Coverage Thresholds & Quality Gates
- **Total Tests in `test_drywall_workflow_e2e.py`**: **38 comprehensive test functions** (30 Tier 1, 5 Tier 2, 1 Tier 3, 2 Tier 4).
- **Total Tests in `test_e2e_workbench.py`**: **25 comprehensive test functions** (17 Tier 1, 5 Tier 2, 1 Tier 3, 2 Tier 4).
- **Combined E2E Tests**: **63 passed tests**, 0 failures, 0 xfails, 100% clean passes on Windows.
- **Zero Cheating Policy**: Genuine mathematical calculations, real PDF vector parsing, genuine openpyxl and PyMuPDF data structures.

---

## 6. Drywall Workflow Test Suite Specification (`tests/test_drywall_workflow_e2e.py`)

### 6.1 Requirement Mapping (R1–R5)
| Req | Area | Tier 1 Tests (>=5 each) | Key Invariants Asserted |
|:---:|:-----|:------------------------|:------------------------|
| **R1** | Partition Schedule Parsing | `test_tier1_r1_01_schedule_sheets_classification`<br>`test_tier1_r1_02_schedule_tag_discovery_exclusion_lumber`<br>`test_tier1_r1_03_extract_wall_materials_schedule_sheets`<br>`test_tier1_r1_04_parse_assembly_attributes_physical_dimensions`<br>`test_tier1_r1_05_material_layers_structured_stack`<br>`test_tier1_r1_06_secondary_detail_sheets_furring_assemblies` | Schedule sheets A-900 (p63) & A-901 (p64) classified; details A-801 (p58), A-802 (p59), A-706 (p52) indexed; lumber callouts (2X4, 2X6) excluded; materials extracted; layers modeled. |
| **R2** | Jev Drywall Classification | `test_tier1_r2_01_probability_filter_threshold_specification`<br>`test_tier1_r2_02_genuine_drywall_tags_qualification`<br>`test_tier1_r2_03_non_drywall_tags_rejection_gl1_gl2_pw`<br>`test_tier1_r2_04_evaluate_with_mock_deterministic_rules`<br>`test_tier1_r2_05_wall_registry_caching_and_persistence`<br>`test_tier1_r2_06_environment_credentials_loader` | Threshold $\ge 0.85$; genuine tags (7A, 1A, 2B, 4B) qualified ($P \ge 0.85$); non-drywall tags (GL1, GL2, PW) rejected ($P < 0.85$); offline mock deterministic rules; registry cache persistence. |
| **R3** | Floor Plan Detection & Marking | `test_tier1_r3_01_floor_plan_tag_geometry_matching`<br>`test_tier1_r3_02_wall_length_measurement_and_collinear_chaining`<br>`test_tier1_r3_03_wall_thickness_measurement_from_casing`<br>`test_tier1_r3_04_visual_highlight_annotations_dual_red`<br>`test_tier1_r3_05_opening_deductions_from_door_arcs`<br>`test_tier1_r3_06_floor_plan_dedup_and_centerline_spine` | Qualified tags matched to CAD linework via leader endpoints and seed segments; gross LF measured; double-line casing separation measured in inches ($4.88"$, $8.50"$, $6.0"$) from $d_{\text{pt}} \times ft\_per\_pt \times 12.0$; dual-red visual annotations rendered; door arc deductions. |
| **R4** | Section Callout & Height Verification | `test_tier1_r4_01_section_callout_tags_parsed_on_floor_plan`<br>`test_tier1_r4_02_navigation_to_referenced_section_detail_sheets`<br>`test_tier1_r4_03_explicit_height_verification_from_detail_elevations`<br>`test_tier1_r4_04_spatial_proximity_callout_association`<br>`test_tier1_r4_05_standard_10ft_height_fallback_and_review_flag`<br>`test_tier1_r4_06_verified_height_status_ok` | Floor plan circular callout bubbles (A-706/08, A-706/09, A-702/01, A-801, A-802/4, A-907/2) parsed; sheet navigation (A-706 $\to$ p52, A-702 $\to$ p48, A-801 $\to$ p58); explicit ceiling heights ($8'-0"$, $7'-8"$, $7'-3"$) extracted; spatial matching within 120 pt radius; fallback to 10.0 ft with review flagging. |
| **R5** | Takeoff Schedule & Live Calculations | `test_tier1_r5_01_takeoff_schedule_compilation_metrics`<br>`test_tier1_r5_02_verified_metrics_saved_in_wall_run`<br>`test_tier1_r5_03_live_recalculation_on_opening_deduction`<br>`test_tier1_r5_04_live_recalculation_on_endpoint_drag`<br>`test_tier1_r5_05_sop_8_7_1_mathematical_parity`<br>`test_tier1_r5_06_review_items_aggregation_in_takeoff` | Gross/net LF, board SF, stud count, runner track LF compiled; verified metrics saved in `WallRun`; live recalculation on door deduction ($\Delta A = -42\text{ SF}$) and endpoint dragging; SOP 8.7.1 exact mathematical parity ($20.00\text{ LF}$, $17.00\text{ LF}$, $358.00\text{ SF}$, 16 studs, $37.00\text{ LF}$ track). |

### 6.2 Tier 2: Boundary & Corner Cases
- `test_tier2_01_out_of_bounds_pages`: Querying boundary/out-of-bounds pages (0, -1, 999) returns clean 404/422 responses without crash.
- `test_tier2_02_single_line_wall_nominal_fallback_thickness`: Single-line walls without parallel twin face fall back cleanly to nominal thickness without `ZeroDivisionError`.
- `test_tier2_03_walls_without_section_tags_fallback_cleanly`: Isolated walls (>120 pt from any callout) fall back to 10.0 ft height with review flag.
- `test_tier2_04_empty_zero_markups_takeoff`: Takeoff calculation with 0 wall runs returns exactly $0.00\text{ LF}$ gross, $0.00\text{ LF}$ net, $0.00\text{ SF}$ board, 0 studs.
- `test_tier2_05_excessive_opening_deduction_clamping`: Opening deduction larger than wall length clamps net LF to $0.00\text{ LF}$ (never negative).

### 6.3 Tier 3: Cross-Feature Workflows
- `test_tier3_end_to_end_drywall_journey`: Multi-step complete workflow:
  1. Schedule parse: discovers tags from schedule sheets A-900 / A-901
  2. Jev classify: verifies qualification with probability $\ge 0.85$
  3. Floor plan trace with thickness: traces wall linework on Sheet A-101 (Page 15)
  4. Section height lookup: associates with section callout and applies verified height
  5. Takeoff compilation & live edit recalculation: asserts updated net LF upon adding door opening

### 6.4 Tier 4: Real-World Blueprint Scenario
- `test_tier4_real_world_blueprint_sheet_a101`: Full automated execution on `uploads/doc_20261104_101950_6cbd34.pdf` targeting Sheet A-101 (Page 15):
  - Scale: `1/8" = 1'-0"` ($ft\_per\_pt = 0.111111$)
  - CAD linework: 5,951 segments, 220 door arcs
  - 31 tag instances located
  - 27 raw wall runs, 19 consolidated runs
  - Gross LF: $495.83 \pm 2.0\text{ LF}$, Net LF: $473.21 \pm 2.0\text{ LF}$, Deductions: $22.62 \pm 1.0\text{ LF}$, Board SF: $> 9,000\text{ SF}$
  - Dual-red visual annotation structures verified
- `test_tier4_real_world_blueprint_sheet_a102`: Full automated execution on Sheet A-102 (Page 16):
  - Scale: `1/8" = 1'-0"` (0.111111 ft/pt, status = DETECTED)
  - CAD linework: 6,587 segments, 180 door arcs
  - Tag instances: $\ge 70$ instances (tags 7A, 2B, 1C, 5E, 8A, 7F, GL1, PW)
  - Non-drywall tags (GL1, PW) segregated/rejected
  - Drywall wall runs traced: Gross LF $> 0$, Net LF $> 0$, Board SF $> 0$


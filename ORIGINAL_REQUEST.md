# Original User Request

## Initial Request — 2026-11-04T11:08:51Z

Deliver a production workbench for drywall estimators by studying the reference code in `protake/` and porting its missing features and capabilities into the project's PDF flow, fixing real-world blueprint wall detection, manual measurement tools, and user interface issues.

Working directory: c:\Users\m.abdullah\Desktop\QTO-PROTOTYPE
Integrity mode: development
The team must NOT:
- Run any git commands.

## Requirements

### R1. Reference Codebase Analysis and Feature Porting
Study the reference codebase in `protake/` (`protake/fastapi`, `protake/frontend`, and audit reports `PDF_QTO_ACCURACY_REPORT.md`, `QTO_ELEMENT_AUDIT.md`, `TRADE_SCOPE_AUDIT.md`) and port its features into the existing project's PDF flow (`fastapi/` and `frontend/`), incorporating its scale calibration, manual markup/ruler tools, wall detection algorithms, and clean estimator UI layout.

### R2. Estimator Workbench UI Streamlining
Streamline the user interface into a clean, functional estimator workbench without clutter, non-functional or broken buttons on either side, dummy drawers, or overlapping headers. Provide clear sheet navigation across multi-page drawing sets, a responsive vector canvas viewer, and an interactive takeoff schedule.

### R3. Interactive Calibration and Markup Tools
Implement interactive canvas tools for estimators:
- 2-point scale calibration: click two points along any known blueprint dimension and enter the distance to calibrate scale interactively.
- Manual wall drawing / ruler tool: click or drag to measure or draw wall runs manually, assigning partition tags and wall height to add them directly to the takeoff schedule.
- Markup editing: click on any wall markup to adjust endpoints, change partition tags, add door/window opening deductions, or delete markups.

### R4. Real-World Blueprint Wall Detection and Takeoff Schedule
Fix wall detection for real-world architectural blueprints (specifically `uploads/doc_20261104_101950_6cbd34.pdf`) so that architectural floor plan sheets detect walls, display dual-red annotations on the canvas viewer, and populate the takeoff schedule with non-zero linear footage (LF) and square footage (SF). Allow estimators to navigate and select specific sheets to analyze.

### R5. Windows Compatibility, Test Suites, and Execution Constraints
CRITICAL CONSTRAINT: Do NOT use any git commands under any circumstances. Ensure all automated test suites pass and the system runs cleanly on Windows.

## Verification Resources
- Test blueprint: `uploads/doc_20261104_101950_6cbd34.pdf`
- Reference project and audit reports: `protake/` (`protake/fastapi`, `protake/frontend`, `PDF_QTO_ACCURACY_REPORT.md`, `QTO_ELEMENT_AUDIT.md`, `TRADE_SCOPE_AUDIT.md`)
- Automated test suites: `tests/`

## Acceptance Criteria

### UI Usability and Layout
- [ ] User interface is streamlined into a clean, functional estimator workbench with no broken buttons, overlapping headers, dummy drawers, or non-functional controls.
- [ ] Sheet navigation functions smoothly across multi-page drawing sets (including 70+ page blueprints).

### Interactive Measurement and Markup
- [ ] Estimator can calibrate sheet scale by clicking two points along a known dimension and entering the distance.
- [ ] Estimator can manually draw or measure a wall run, assign partition tag and height, and see it added to the takeoff schedule.
- [ ] Estimator can click existing wall markups to adjust endpoints, change partition tags, add door/window opening deductions, or delete markups.

### Real-World Blueprint Detection
- [ ] Processing architectural floor plan sheets in `uploads/doc_20261104_101950_6cbd34.pdf` detects wall runs and returns non-zero linear footage (LF) and square footage (SF).
- [ ] Detected walls are displayed as dual-red visual annotations on the canvas viewer and populate the takeoff schedule.
- [ ] Estimator can select specific floor plan sheets to analyze rather than processing the entire multi-page document unconditionally.

### Constraints and Verification
- [ ] No git commands are executed during development, testing, or verification.
- [ ] All automated test suites in `tests/` pass cleanly on Windows.


## Follow-up — 2026-11-04T11:20:28Z

User Directive Received (2026-11-04T11:20:28Z):
"first study the systems functionalit in the protake folder some features are already implemented, implement and integrate the rest"

Please ensure the team thoroughly inspects what features are already built and working in protake/ and focuses on implementing and cleanly integrating the rest into the PDF pipeline and estimator workbench.
Remember: strictly no git commands under any circumstances. Ensure this directive is reflected in your survey synthesis and milestone planning.

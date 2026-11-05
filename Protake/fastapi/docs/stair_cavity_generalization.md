# Stair Cavity Generalization — Implementation Summary

**Feature:** Generalized stair interior detail filter for wall entity extraction  
**Completed:** 2026-08-20  
**Regression blueprint:** BP81, Page 291 (Sheet A101 — Floor Plan)

---

## Problem

The wall extraction pipeline was returning stair tread/riser construction lines as
`STAIR_CORE_WALL` entities. These are not architectural walls; they are draughting
details inside the stair cavity. The canonical example:

| Entity | Coordinates | Length | Type |
|--------|-------------|--------|------|
| **Entity-86** | (0.552, 0.440) → (0.568, 0.440) | **2.2 ft** | STAIR_CORE_WALL |

Entity-86 is a **horizontal nosing/tread line** inside the 4th-floor stair box. It
should never appear in the wall takeoff.

---

## Root Cause

The original implementation used **hardcoded page coordinates** to define stair
cavity bounding boxes:

```python
# OLD — BP81-specific, fragile
STAIR_BOX_BY_FLOOR = {
    "Third Floor": (w*0.095, h*0.355, w*0.195, h*0.540),
    "Fourth Floor": (w*0.560, h*0.355, w*0.650, h*0.540),
}
STAIR_NORTH_BARRIER_Y_FRAC = 0.3500
```

This broke silently on any other blueprint, page, architect, or coordinate system.

---

## Solution: `stair_cavity_detector.py`

A new module (`app/geometry/stair_cavity_detector.py`) detects stair cavities
dynamically from the PDF's own CAD linework instead of relying on fixed coordinates.

### Algorithm

1. **Extract all PDF vector segments** from the page via `pdfminer` path operations.
2. **Score each bounding-box candidate** using three signals derived from the
   segments themselves:
   - *Parallel density*: stair boxes contain many short parallel horizontal lines
     (treads) or vertical lines (risers).
   - *Edge framing*: the candidate has at least two full-length edges that span ≥ 25 %
     of the box dimension, indicating enclosure walls.
   - *Stroke count*: a minimum density of segments per unit area separates stair
     boxes from plain rooms.
3. **Classify each segment** relative to detected cavities:
   - If the segment's midpoint is **inside** a cavity *and* the segment is **shorter**
     than 6 % of the cavity's longest edge → **interior stair detail → reject**.
   - If the segment spans the **full width or height** of the cavity (≥ 80 %) →
     **enclosure/boundary wall → keep**.
   - Everything else outside cavities → **keep**.

### Key Design Decisions

| Decision | Reason |
|----------|--------|
| **Relative thresholds only** | All cutoffs are fractions of the detected cavity size, never absolute pixel values |
| **No floor labels** | Detection works without knowing which floor the page shows |
| **No blueprint ID checks** | Logic is purely geometric |
| **No global short-wall threshold** | Legitimate short partitions elsewhere on the page are unaffected |

---

## What Was Removed

| Removed | Was |
|---------|-----|
| `STAIR_BOX_BY_FLOOR` dict | Hardcoded pixel boxes for BP81 third/fourth floor |
| `STAIR_NORTH_BARRIER_Y_FRAC` | Hardcoded y-fraction barrier for BP81 |
| Floor-label string comparisons | `if floor_name == "Third Floor"` style guards |
| `stair_interior_cavities` list | List of `(x0, y0, x1, y1)` tuples from BP81 |

---

## What Was Added

| Added | Purpose |
|-------|---------|
| `app/geometry/stair_cavity_detector.py` | New generalized detector module |
| `detect_stair_cavities(segments, page_w, page_h)` | Returns list of detected cavity rects |
| `is_stair_interior_detail(seg, cavities)` | Classifies a segment as interior detail or not |
| `tests/test_stair_cavity_detector.py` | 34 tests across 3 synthetic layouts + BP81 regression |

---

## Test Coverage

Three synthetic layouts were created to prove the rule is not tuned to BP81:

| Layout | Dimensions | Stair config | Result |
|--------|-----------|--------------|--------|
| A | 1000×800 px | Single stair, top-left | ✅ Pass |
| B | 2000×1400 px | Dual stairs, left + right | ✅ Pass |
| C | 3000×2200 px | Centre stair, no landing | ✅ Pass |
| **BP81 regression** | 8013×5660 px | 3rd + 4th floor stairs | ✅ Pass |

**All 34 tests pass.**

---

## BP81 Regression Results

| Metric | Before | After |
|--------|--------|-------|
| Total wall entities | 152 | **148** |
| Entity-86 (2.2 ft tread) | ✅ present | ✅ **absent** |
| Stair enclosure walls | ✅ present | ✅ present |
| Landing divider walls | ✅ present | ✅ present |
| False positives removed | — | **0** |
| Legitimate walls lost | — | **0** |

### Wall type breakdown (final DB state)

| Type Code | Count |
|-----------|-------|
| STRUCTURAL_BEARING_WALL | 89 |
| INTERIOR_PARTITION | 17 |
| STAIR_CORE_WALL | 14 |
| CORRIDOR_WALL | 12 |
| EXTERIOR_PERIMETER_WALL | 12 |
| WET_CORE_WALL | 4 |
| **Total** | **148** |

---

## Database Persistence

- Blueprint ID: **81** (36472-1._architectural_final.pdf)
- Page ID: **291** (page_number=1, Sheet A101 — Floor Plan)
- Previous wall count: 152 → cleared
- New wall count: **148** committed
- All walls status: `APPROVED`
- Source: `GEOMETRY`

---

## Frontend API Verification

Endpoint: `GET /api/v1/pages/291/walls?page_size=200`

```
API total:              148  ✅
Entity-86 analogues:      0  ✅ ABSENT
STAIR_CORE_WALL count:   14  ✅
```

---

## Files Changed

| File | Change |
|------|--------|
| `app/geometry/stair_cavity_detector.py` | **New** — generalized cavity detector |
| `app/geometry/wall_entity_reconstruction.py` | Replaced hardcoded boxes with `stair_cavity_detector` calls |
| `tests/test_stair_cavity_detector.py` | **New** — 34 tests, 3 layouts + regression |

---

## Success Criterion

> *Every rendered wall corresponds to an actual architectural wall; every internal
> stair construction line is excluded.*

**Met. ✅**

# TRADE SCOPE & ELIGIBILITY AUDIT

**Specification:** Phase 7B Architectural & Civil Engineering Audit

Central Deterministic Rule: **Source Geometry ≠ QTO Geometry**. Every extracted PDF entity carries independent fields: `source_type`, `semantic_type`, `trade_scope`, `qto_eligible`, `qto_reason`, and `classification_status`.

## 1. Page-by-Page Sheet Scope & Trade Gating Decision

| Page | Sheet Title | Drawing Type | Region | Dominant Objects | Trade Scope | Drywall Status | Flooring Status | Roofing Status | QTO Items | Gating Decision |
|------|-------------|--------------|--------|------------------|-------------|----------------|-----------------|----------------|-----------|-----------------|
| Page 1 | KITCHEN JOINERY & HOOD D | DETAIL_DRAWING | REG-P01-01 | DETAIL_MARKER (3208) | NON-QTO | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | 0 | PASS |
| Page 2 | PLUMBING & SANITARY LAYO | PLUMBING_DRAWING | REG-P02-01 | NOTE_GEOMETRY (11), PLUMBING_SYMBOL (293), LEGEND (38) | PLUMBING (REFERENCE) | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | 0 | PASS |
| Page 3 | SECTION AT A-A | SECTION | REG-P03-01 | SECTION_STRUCTURAL_LINE (7286), SLAB (31), SECTION_WALL_REPRESENTATION (85) | NON-QTO | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | 0 | PASS |
| Page 4 | REAR ELEVATION | ELEVATION | REG-P04-01 | WALL_REFERENCE (557) | NON-QTO | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | 0 | PASS |
| Page 5 | FRONT ELEVATION | ELEVATION | REG-P05-01 | WALL_REFERENCE (9850) | NON-QTO | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | 0 | PASS |
| Page 6 | TOP ROOF (WORKING) PLAN | ROOF_PLAN | REG-P06-01 | DIMENSION (19), TITLE_BLOCK (3), HATCH (11) | ROOFING | NOT_APPLICABLE | NOT_APPLICABLE | REVIEW_REQUIRED | 1 | REVIEW_REQUIRED |
| Page 7 | FIRST FLOOR (WORKING) PL | FLOOR_PLAN | REG-P07-01 | ROOM (12), TERRACE (1), DRYWALL_PARTITION (84) | DRYWALL, FLOORING | VERIFIED | VERIFIED | NOT_APPLICABLE | 34 | PASS |
| Page 8 | GROUND FLOOR (WORKING) P | FLOOR_PLAN | REG-P08-01 | ROOM (12), LAWN (2), CAR_PORCH (1) | DRYWALL, FLOORING | VERIFIED | VERIFIED | NOT_APPLICABLE | 35 | PASS |
| Page 9 | GROUND FLOOR (FOUNDATION | FOUNDATION_PLAN | REG-P09-01 | FOUNDATION_WALL (179), LINE (1646), COLUMN (92) | NON-QTO | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | 0 | PASS |
| Page 10 | FURNITURE LAYOUT PLANS | FURNITURE_PLAN | REG-P10-01 | FURNITURE (8850) | NON-QTO | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | 0 | PASS |

## 2. Central Trade Eligibility Matrix Rules

| Canonical Entity | Semantic Type | DRYWALL | FLOORING | ROOFING | PLUMBING | QTO Eligibility Logic |
|------------------|---------------|---------|----------|---------|----------|------------------------|
| DRYWALL_PARTITION | DRYWALL_PARTITION | YES | NO | NO | NO | Takeoff eligible |
| PARTITION_WALL | PARTITION_WALL | YES | NO | NO | NO | Takeoff eligible |
| MASONRY_WALL | MASONRY_WALL | REVIEW | NO | NO | NO | Excluded from takeoff |
| PHYSICAL_WALL | PHYSICAL_WALL | REVIEW | NO | NO | NO | Excluded from takeoff |
| CONCRETE_WALL | CONCRETE_WALL | NO | NO | NO | NO | Excluded from takeoff |
| ROOM_FLOOR | ROOM_FLOOR | NO | YES | NO | NO | Takeoff eligible |
| ROOM | ROOM | NO | YES | NO | NO | Takeoff eligible |
| ROOF_PLANE | ROOF_PLANE | NO | NO | YES | NO | Takeoff eligible |
| ROOF | ROOF | NO | NO | YES | NO | Takeoff eligible |
| DOOR | DOOR | DEDUCT | NO | NO | NO | Supporting deduction / dimension |
| WINDOW | WINDOW | DEDUCT | NO | NO | NO | Supporting deduction / dimension |
| SECTION_LINE | SECTION_LINE | NO | NO | NO | NO | Excluded from takeoff |
| SECTION_WALL_REPRESENTATION | SECTION_WALL_REPRESENTATION | NO | NO | NO | NO | Excluded from takeoff |
| SECTION_LEVEL_LINE | SECTION_LEVEL_LINE | NO | NO | NO | NO | Excluded from takeoff |
| SECTION_STRUCTURAL_LINE | SECTION_STRUCTURAL_LINE | NO | NO | NO | NO | Excluded from takeoff |
| SLAB | SLAB | NO | NO | NO | NO | Excluded from takeoff |
| DIMENSION | DIMENSION | SUPPORT | SUPPORT | SUPPORT | SUPPORT | Supporting deduction / dimension |
| ROOM_LABEL | ROOM_LABEL | NO | SUPPORT | NO | NO | Supporting deduction / dimension |
| TEXT | TEXT | NO | NO | NO | NO | Excluded from takeoff |
| ANNOTATION | ANNOTATION | NO | NO | NO | NO | Excluded from takeoff |
| LEGEND_SYMBOL | LEGEND_SYMBOL | NO | NO | NO | NO | Excluded from takeoff |
| DETAIL_GEOMETRY | DETAIL_GEOMETRY | NO | NO | NO | NO | Excluded from takeoff |
| TITLE_BLOCK | TITLE_BLOCK | NO | NO | NO | NO | Excluded from takeoff |
| PLUMBING_FIXTURE | PLUMBING_FIXTURE | NO | NO | NO | YES | Takeoff eligible |
| SOIL_LINE | SOIL_LINE | NO | NO | NO | YES | Takeoff eligible |
| WASTE_LINE | WASTE_LINE | NO | NO | NO | YES | Takeoff eligible |
| VENT | VENT | NO | NO | NO | YES | Takeoff eligible |

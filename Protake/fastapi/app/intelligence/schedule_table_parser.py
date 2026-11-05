"""Table-Aware Spatial Partition Schedule Parser.

Extracts structured partition assembly specifications, stud framing, drywall layers,
and acoustic/fire ratings from authoritative PDF schedule sheets using spatial table grids.
Preserves exact table cell coordinates for forensic assembly evidence.
"""

import re
from typing import Any
import fitz
from app.models.architectural_wall import WallAssemblySpec


# Wall tag identification regex: matches NR-1, NR-2, W1, W2, PT-01, F-1, X-1,
# TYPE-A, TYPE A, P1, P2, EW-1, EW1, etc. EW/TYPE accept hyphen, space, or no
# separator — real drawings use all three forms.
TAG_CELL_PATTERN = re.compile(
    r"^\s*(NR-\d{1,2}|F-\d{1,2}|X-\d{1,2}|PT-\d{1,2}|EW[-\s]?\d{1,2}|TYPE[-\s]?[A-Z]|P\d{1,2}|W[1-9]|[A-Z]{1,3}-\d{1,2})\b",
    re.IGNORECASE,
)


def _spec_fields(spec: WallAssemblySpec) -> tuple:
    """The substantive fields that make two schedule definitions of the same
    tag actually *different* assemblies, as opposed to the same assembly
    parsed twice (e.g. duplicated on an index sheet)."""
    return (
        round(spec.stud_depth_in, 3),
        spec.board_type_side_a,
        spec.layers_side_a,
        spec.board_type_side_b,
        spec.layers_side_b,
        spec.fire_rating_hr,
    )


def _merge_with_conflict_detection(
    existing: dict[str, dict[str, Any]], new: dict[str, dict[str, Any]]
) -> None:
    """Merges `new` schedule entries into `existing` in place. When the same
    tag is already defined with a substantively different assembly on a
    DIFFERENT sheet, this never silently picks one (the previous behavior of
    a plain dict.update() blind-overwrite) — it keeps the first entry found,
    flags it conflicted, and records both definitions so the wall pipeline
    can route the wall to NEEDS_REVIEW / MULTIPLE_SCHEDULE_DEFINITIONS
    instead of trusting an arbitrarily "winning" spec.
    """
    for tag_key, entry in new.items():
        prior = existing.get(tag_key)
        if prior is None:
            existing[tag_key] = entry
            continue

        prior_spec = prior.get("assembly_definition")
        new_spec = entry.get("assembly_definition")
        same_sheet = prior.get("schedule_sheet") == entry.get("schedule_sheet")
        same_spec = (
            isinstance(prior_spec, WallAssemblySpec)
            and isinstance(new_spec, WallAssemblySpec)
            and _spec_fields(prior_spec) == _spec_fields(new_spec)
        )
        if same_sheet or same_spec:
            # Genuinely the same definition (or a duplicate parse of the same
            # sheet) — not a conflict, nothing to flag.
            continue

        conflict_sources = list(prior.get("conflict_sources") or [])
        if not conflict_sources:
            conflict_sources.append({
                "sheet": prior.get("schedule_sheet"),
                "source_page": prior.get("source_page"),
                "definition": getattr(prior_spec, "description", None),
            })
        conflict_sources.append({
            "sheet": entry.get("schedule_sheet"),
            "source_page": entry.get("source_page"),
            "definition": getattr(new_spec, "description", None),
        })
        existing[tag_key] = {
            **prior,
            "verified": False,
            "conflicted": True,
            "conflict_reason": "MULTIPLE_SCHEDULE_DEFINITIONS",
            "conflict_sources": conflict_sources,
        }


class ScheduleTableParser:
    """Extracts partition assembly specifications from vector table grids in PDF sheets."""

    def parse_pdf_document_schedules(
        self, pdf_path: str, target_pages: list[int] | None = None
    ) -> dict[str, dict[str, Any]]:
        """Scans candidate pages in a multi-page PDF for partition schedule tables.

        Returns a dictionary mapping tag -> assembly evidence dictionary:
        {
            "tag": "NR-2",
            "schedule_sheet": "A7.1",
            "source_page": 7,
            "source_region": {"x0": ..., "y0": ..., "x1": ..., "y1": ...},
            "assembly_definition": WallAssemblySpec(...),
            "verified": True
        }
        """
        discovered_assemblies: dict[str, dict[str, Any]] = {}
        try:
            doc = fitz.open(pdf_path)
            target_set = set(target_pages) if target_pages else None
            for page_idx, page in enumerate(doc):
                page_num = page_idx + 1
                if target_set is not None and page_num not in target_set:
                    continue

                page_text = page.get_text()
                # Fast check: skip vector table extraction if page text lacks any partition/schedule keywords
                if not any(kw in page_text.upper() for kw in ("PARTITION", "WALL TYPE", "SCHEDULE", "ASSEMBLY", "STUD", "FRAMING", "GYPSUM", "GWB")):
                    continue

                sheet_num = self._extract_sheet_number(page) or f"Sheet-{page_num}"

                # Check for vector tables on this page
                page_found_any = False
                tables = page.find_tables()
                if tables and len(tables.tables) > 0:
                    for table in tables.tables:
                        extracted_rows = table.extract()
                        bbox = {
                            "x0": round(table.bbox[0] / page.rect.width, 4),
                            "y0": round(table.bbox[1] / page.rect.height, 4),
                            "x1": round(table.bbox[2] / page.rect.width, 4),
                            "y1": round(table.bbox[3] / page.rect.height, 4),
                        }
                        parsed = self.parse_table_grid(extracted_rows, sheet_num, page_num, bbox)
                        if parsed:
                            page_found_any = True
                        _merge_with_conflict_detection(discovered_assemblies, parsed)

                # Spatial row-grouping fallback for schedules formatted as aligned text
                # blocks. Gated on THIS page's own result, not the whole document's
                # accumulated dict: an early page whose table happens to match the tag
                # pattern (a lighting/RCP legend's fixture codes are frequently
                # indistinguishable from partition tags by regex alone) must not
                # permanently disable the fallback for every later page, including
                # whichever page actually carries the real partition-schedule text.
                if not page_found_any:
                    spatial_parsed = self.parse_spatial_text_schedule(page, sheet_num, page_num)
                    _merge_with_conflict_detection(discovered_assemblies, spatial_parsed)

        except Exception as exc:
            print(f"[ScheduleTableParser] Notice reading {pdf_path}: {exc}")

        return discovered_assemblies

    def parse_table_grid(
        self,
        rows: list[list[str | None]],
        sheet_number: str,
        page_number: int,
        table_bbox: dict[str, float],
    ) -> dict[str, dict[str, Any]]:
        """Parses a 2D extracted table grid into validated assembly evidence records."""
        results: dict[str, dict[str, Any]] = {}
        if not rows or len(rows) < 2:
            return results

        # Determine column indices from header row
        header = [str(c).upper().strip() if c else "" for c in rows[0]]
        tag_col = self._find_col(header, ["TYPE", "TAG", "MARK", "WALL TYPE", "PARTITION", "SYM", "P"])
        desc_col = self._find_col(header, ["DESCRIPTION", "CONSTRUCTION", "ASSEMBLY", "SPECIFICATION", "REMARKS"])
        stud_col = self._find_col(header, ["STUD", "FRAMING", "CORE", "DEPTH", "SIZE"])
        board_col = self._find_col(header, ["BOARD", "DRYWALL", "GYPSUM", "GWB", "LAYERS", "LINING"])
        fire_col = self._find_col(header, ["FIRE", "RATING", "HR", "HOURLY"])
        stc_col = self._find_col(header, ["STC", "SOUND", "ACOUSTIC"])

        has_partition_header = bool(
            stud_col is not None
            or board_col is not None
            or any("PARTITION" in h or "WALL" in h for h in header)
        )

        for row_idx, row in enumerate(rows[1:], start=1):
            if not row:
                continue
            cells = [str(c).strip() if c else "" for c in row]

            # Find tag candidate
            tag = None
            if tag_col is not None and tag_col < len(cells) and cells[tag_col]:
                match = TAG_CELL_PATTERN.match(cells[tag_col])
                if match:
                    tag = match.group(1).upper()

            if not tag:
                # Search all cells in row for a tag pattern
                for c in cells:
                    match = TAG_CELL_PATTERN.match(c)
                    if match:
                        tag = match.group(1).upper()
                        break

            if not tag:
                continue

            # Assemble description text
            desc_parts = []
            if desc_col is not None and desc_col < len(cells) and cells[desc_col]:
                desc_parts.append(cells[desc_col])
            if stud_col is not None and stud_col < len(cells) and cells[stud_col]:
                desc_parts.append(f"Stud: {cells[stud_col]}")
            if board_col is not None and board_col < len(cells) and cells[board_col]:
                desc_parts.append(f"Board: {cells[board_col]}")
            if fire_col is not None and fire_col < len(cells) and cells[fire_col]:
                desc_parts.append(f"Fire: {cells[fire_col]}")
            if stc_col is not None and stc_col < len(cells) and cells[stc_col]:
                desc_parts.append(f"STC: {cells[stc_col]}")

            # If explicit columns weren't found, concatenate non-empty row cells
            full_desc = " | ".join(desc_parts) if desc_parts else " | ".join(c for c in cells if c and c != tag)
            if not full_desc:
                full_desc = f"Partition Assembly {tag}"

            desc_upper = full_desc.upper()

            # Reject electrical / mechanical / lighting fixture schedules (e.g. Heaters, Downlights, Pendants)
            is_fixture = any(
                kw in desc_upper
                for kw in ("HEATER", "DOWNLIGHT", "LIGHT", "FIXTURE", "DIFFUSER", "RECESSED", "LANTERN", "PENDANT", "LUMINAIRE", "SPEAKER", "SPRINKLER", "KENALL", "BROMIC", "KICHLER")
            )
            has_wall_evidence = any(
                kw in desc_upper
                for kw in ("STUD", "FRAMING", "DRYWALL", "GYPSUM", "GWB", "FIRE RATING", "1 HR", "2 HR", "1-HR", "2-HR", "PARTITION", "WALL TYPE", "WALL ASSEMBLY", "STC", "ACOUSTIC", "PLASTER", "FURR")
            )
            if is_fixture and not ("STUD" in desc_upper or "DRYWALL" in desc_upper or "GWB" in desc_upper or "GYPSUM" in desc_upper):
                continue
            if not (has_partition_header or has_wall_evidence):
                continue

            spec = self._parse_assembly_spec_from_text(tag, full_desc, source=f"schedule_table_{sheet_number}")

            results[tag] = {
                "tag": tag,
                "schedule_sheet": sheet_number,
                "source_page": page_number,
                "source_region": table_bbox,
                "assembly_definition": spec,
                "verified": True,
            }

        return results

    def parse_spatial_text_schedule(
        self, page: fitz.Page, sheet_number: str, page_number: int
    ) -> dict[str, dict[str, Any]]:
        """Spatial text fallback: clusters aligned text words into schedule row definitions."""
        results: dict[str, dict[str, Any]] = {}
        text = page.get_text()
        lines = text.splitlines()

        for line in lines:
            line_str = line.strip()
            match = re.match(r"^([A-Z]{1,3}-\d{1,2}|W\d{1,2}|PT-\d{1,2}|TYPE-[A-Z]|P\d{1,2})\s*[:\-\s]\s*(.+)$", line_str, re.IGNORECASE)
            if match:
                tag = match.group(1).upper()
                desc = match.group(2).strip()
                desc_upper = desc.upper()
                is_fixture = any(
                    kw in desc_upper
                    for kw in ("HEATER", "DOWNLIGHT", "LIGHT", "FIXTURE", "DIFFUSER", "RECESSED", "LANTERN", "PENDANT", "LUMINAIRE", "SPEAKER", "SPRINKLER", "KENALL", "BROMIC", "KICHLER")
                )
                has_wall_evidence = any(
                    kw in desc_upper
                    for kw in ("STUD", "FRAMING", "DRYWALL", "GYPSUM", "GWB", "FIRE RATING", "1 HR", "2 HR", "1-HR", "2-HR", "PARTITION", "WALL TYPE", "WALL ASSEMBLY", "STC", "ACOUSTIC", "PLASTER", "FURR")
                )
                if is_fixture and not ("STUD" in desc_upper or "DRYWALL" in desc_upper or "GWB" in desc_upper or "GYPSUM" in desc_upper):
                    continue
                if len(desc) >= 5 and has_wall_evidence:
                    spec = self._parse_assembly_spec_from_text(tag, desc, source=f"schedule_notes_{sheet_number}")
                    results[tag] = {
                        "tag": tag,
                        "schedule_sheet": sheet_number,
                        "source_page": page_number,
                        "source_region": {"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0},
                        "assembly_definition": spec,
                        "verified": True,
                    }
        return results

    def _parse_assembly_spec_from_text(self, tag: str, desc: str, source: str) -> WallAssemblySpec:
        """Parses physical assembly specification attributes from raw schedule description text."""
        desc_upper = desc.upper()

        # Stud depth extraction
        stud_depth = 3.625
        stud_match = re.search(r"(\d+[\s\-/]*\d*[\"']?)\s*(?:METAL|STEEL|WOOD|TRACK|CH)?\s*STUD", desc_upper)
        if stud_match:
            s_str = stud_match.group(1).replace("\"", "").replace("'", "").strip()
            if "6" in s_str:
                stud_depth = 6.0
            elif "2-1/2" in s_str or "2.5" in s_str:
                stud_depth = 2.5
            elif "3-5/8" in s_str or "3.625" in s_str or "4" in s_str:
                stud_depth = 3.625
            elif "7/8" in s_str or "0.875" in s_str:
                stud_depth = 0.875

        # Furring channel check
        if "FURR" in desc_upper or "7/8" in desc_upper:
            stud_depth = 0.875

        # Layers & Sides to hang
        layers_a = 2 if ("2 LAYER" in desc_upper or "DOUBLE LAYER" in desc_upper or "2 LAYERS" in desc_upper) else 1
        if "1 SIDE" in desc_upper or "ONE SIDE" in desc_upper or "FURRED" in desc_upper:
            layers_b = 0
            sides = 1
        elif "EXISTING" in desc_upper and "REMAIN" in desc_upper:
            layers_a = 0
            layers_b = 0
            sides = 0
        else:
            layers_b = 1
            sides = 2

        # Board type
        board_type = (
            "5/8\" Type X GWB" if ("TYPE X" in desc_upper or "FIRE" in desc_upper) else (
                "5/8\" Mold/Moisture Resistant GWB" if ("MOLD" in desc_upper or "MOISTURE" in desc_upper or "WET" in desc_upper) else (
                    "1/2\" Regular GWB" if "1/2" in desc_upper else "5/8\" GWB"
                )
            )
        )

        # Fire rating
        fire_rating = (
            2.0 if ("2 HR" in desc_upper or "2-HOUR" in desc_upper or "2HR" in desc_upper) else (
                1.0 if ("1 HR" in desc_upper or "1-HOUR" in desc_upper or "1HR" in desc_upper) else 0.0
            )
        )

        # STC acoustic rating
        stc = None
        stc_match = re.search(r"STC\s*(\d{2})", desc_upper)
        if stc_match:
            stc = float(stc_match.group(1))
        elif "SOUND" in desc_upper or "ACOUSTIC" in desc_upper:
            stc = 50.0

        return WallAssemblySpec(
            tag=tag,
            description=desc,
            stud_depth_in=stud_depth,
            # GAP-G FIX: derive gauge from description text, not a hardcoded constant.
            # 20 GA for standard partitions ≥ 3-5/8" depth, 25 GA for light/shallow.
            stud_gauge=self._parse_stud_gauge(desc_upper, stud_depth),
            board_type_side_a=board_type,
            layers_side_a=layers_a,
            board_type_side_b=board_type if sides == 2 else "None",
            layers_side_b=layers_b,
            sides_to_hang=sides,
            insulation="R-11 Sound Batt" if ("BATT" in desc_upper or "INSULATION" in desc_upper or "SOUND" in desc_upper) else None,
            fire_rating_hr=fire_rating,
            sound_rating_stc=stc or (45.0 if sides == 2 else 35.0),
            source=source,
        )

    def _find_col(self, header: list[str], keywords: list[str]) -> int | None:
        for idx, col_name in enumerate(header):
            if any(kw in col_name for kw in keywords):
                return idx
        return None

    def _parse_stud_gauge(self, desc_upper: str, stud_depth_in: float) -> str:
        """Derive stud gauge from schedule text.

        GAP-G FIX: Replaces the previous `"20 GA" if stud_depth >= 3.625 else "25 GA"`
        which lost explicit gauge callouts (e.g. a 3-5/8" 25 GA light partition was
        overridden to 20 GA simply because the depth matched).

        Priority:
        1. Explicit gauge callout in the description text
        2. Fire/rated assembly → 20 GA minimum (per IBC and ASTM C645)
        3. Furring channel → 25 GA always
        4. Depth-based inference:
              ≥ 6" → 20 GA (heavy-duty framing)
              ≥ 3.625" < 6" → 20 GA (standard commercial partition)
              < 3.625" → 25 GA (light partition, furring)
        """
        # 1. Explicit callout
        if "18 GA" in desc_upper or "18GA" in desc_upper:
            return "18 GA"
        if "20 GA" in desc_upper or "20GA" in desc_upper:
            return "20 GA"
        if "25 GA" in desc_upper or "25GA" in desc_upper:
            return "25 GA"
        if "16 GA" in desc_upper or "16GA" in desc_upper:
            return "16 GA"

        # 2. Fire-rated → 20 GA minimum
        if any(kw in desc_upper for kw in ("FIRE", "1 HR", "2 HR", "1-HOUR", "2-HOUR", "1HR", "2HR")):
            return "20 GA"

        # 3. Furring
        if "FURR" in desc_upper or "7/8" in desc_upper:
            return "25 GA"

        # 4. Depth-based
        if stud_depth_in >= 3.625:
            return "20 GA"
        return "25 GA"

    def _extract_sheet_number(self, page: fitz.Page) -> str | None:
        text = page.get_text()
        sheet_match = re.search(r"(?:SHEET|DWG|DR NO\.|DRAWING NO\.)\s*[:\.]?\s*([A-Z0-9\.\-]+)", text, re.IGNORECASE)
        if sheet_match:
            return sheet_match.group(1).upper()
        # Look for sheet pattern like A10.2, A7.1, A2.1, A-601
        standalone = re.search(r"\b(A\d{1,2}\.\d{1,2}|A-\d{3}|A\d{1,2})\b", text)
        if standalone:
            return standalone.group(1).upper()
        return None

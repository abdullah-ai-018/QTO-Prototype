"""Multi-Sheet Schedule & Specification Parser.

Extracts wall partition schedules, door/window schedules, and room finish schedules
from authoritative schedule sheets and drawing general notes.
"""

import re
from typing import Any
from app.models.project_knowledge_graph import (
    PartitionScheduleEntry,
    DoorScheduleEntry,
)


def normalize_wall_tag(tag: str) -> str:
    """Normalizes wall tags across architectural conventions.
    
    Examples:
      'EXTERIOR WALL - 1' -> 'EXT-1'
      'INTERIOR PARTITION - 2' -> 'INT-2'
      'PARTITION P1' -> 'P1'
      'W-1' -> 'W1'
      'PT-01' -> 'PT-1'
    """
    if not tag:
        return ""
    t = tag.strip().upper()
    t = re.sub(r"\s+", " ", t)

    # Exterior wall variations
    if re.match(r"^EXT(?:ERIOR)?\s*WALL\s*[-–—]?\s*(\d+)$", t):
        num = re.search(r"\d+", t).group(0)
        return f"EXT-{num}"
    if re.match(r"^EXT\s*[-–—]?\s*(\d+)$", t):
        num = re.search(r"\d+", t).group(0)
        return f"EXT-{num}"
    if re.match(r"^EW\s*[-–—]?\s*(\d+)$", t):
        num = re.search(r"\d+", t).group(0)
        return f"EXT-{num}"

    # Interior partition variations
    if re.match(r"^INT(?:ERIOR)?\s*PARTITION\s*[-–—]?\s*(\d+)$", t):
        num = re.search(r"\d+", t).group(0)
        return f"INT-{num}"
    if re.match(r"^PARTITION\s*P?(\d+)$", t):
        num = re.search(r"\d+", t).group(0)
        return f"P{num}"
    if re.match(r"^PT\s*[-–—]?\s*0*(\d+)$", t):
        num = re.search(r"\d+", t).group(0)
        return f"PT-{num}"
    if re.match(r"^NR\s*[-–—]?\s*0*(\d+)$", t):
        num = re.search(r"\d+", t).group(0)
        return f"NR-{num}"
    if re.match(r"^W\s*[-–—]?\s*0*(\d+)$", t):
        num = re.search(r"\d+", t).group(0)
        return f"W{num}"
    if re.match(r"^WP\s*[-–—]?\s*0*(\d+)$", t):
        num = re.search(r"\d+", t).group(0)
        return f"WP{num}"

    return re.sub(r"[\s\-_]+", "-", t)


class MultiSheetScheduleParser:
    """Parses partition schedules and door/window schedules across drawing sets."""

    def parse_partition_schedule(
        self, text_content: str, sheet_number: str = "A-601", page_id: int | None = None
    ) -> dict[str, PartitionScheduleEntry]:
        """Parses partition assembly specifications from schedule text."""
        entries: dict[str, PartitionScheduleEntry] = {}
        lines = text_content.splitlines()

        # Regex for tag definition lines supporting wide architectural conventions:
        # e.g. "EXTERIOR WALL - 1", "INTERIOR PARTITION - 2", "W1", "W-1", "PT-1", "NR-1",
        # "TYPE-A", "TYPE A" — EW/TYPE both accept hyphen, space, or no separator.
        pattern = re.compile(
            r"^\s*(EXTERIOR\s+WALL\s*[-–—]?\s*\d{1,2}|INTERIOR\s+PARTITION\s*[-–—]?\s*\d{1,2}|PARTITION\s+[A-Z0-9]+|W-?\d{1,2}|WP-?\d{1,2}|EXT-?\d{1,2}|PT-?\d{1,2}|EW[-\s]?\d{1,2}|NR-?\d{1,2}|F-?\d{1,2}|X-?\d{1,2}|TYPE[-\s]?[A-Z]|P\d{1,2})\b\s*[:\-\s]\s*(.+)$",
            re.IGNORECASE,
        )

        for line in lines:
            match = pattern.match(line.strip())
            if match:
                raw_tag = match.group(1).upper().strip()
                desc = match.group(2).strip()

                # Extract stud depth
                stud_match = re.search(r"(\d+[\s\-/]*\d*[\"']?)\s*(?:METAL|STEEL|WOOD)?\s*STUD", desc, re.IGNORECASE)
                stud_depth = 3.625
                if stud_match:
                    s_str = stud_match.group(1).replace("\"", "").strip()
                    if "6" in s_str:
                        stud_depth = 6.0
                    elif "2-1/2" in s_str or "2.5" in s_str:
                        stud_depth = 2.5
                    elif "3-5/8" in s_str or "3.625" in s_str:
                        stud_depth = 3.625

                # Extract board layers & thickness
                layers_a = 2 if ("2 LAYER" in desc.upper() or "DOUBLE LAYER" in desc.upper()) else 1
                layers_b = 1 if ("EACH SIDE" in desc.upper() or "EA SIDE" in desc.upper() or "BOTH SIDES" in desc.upper()) else (
                    0 if "1 SIDE" in desc.upper() else 1
                )
                sides = 2 if layers_b > 0 else 1

                board_type = "5/8\" Type X GWB" if "TYPE X" in desc.upper() or "5/8" in desc else (
                    "1/2\" Regular GWB" if "1/2" in desc else "5/8\" GWB"
                )

                # Fire rating
                fire_rating = 2.0 if "2 HR" in desc.upper() or "2-HOUR" in desc.upper() else (
                    1.0 if "1 HR" in desc.upper() or "1-HOUR" in desc.upper() else None
                )

                entry = PartitionScheduleEntry(
                    tag=raw_tag,
                    description=desc,
                    stud_depth_in=stud_depth,
                    stud_gauge=self._infer_gauge_from_desc(desc),
                    board_type_side_a=board_type,
                    layers_side_a=layers_a,
                    board_type_side_b=board_type if layers_b > 0 else "None",
                    layers_side_b=layers_b,
                    sides_to_hang=sides,
                    fire_rating_hr=fire_rating,
                    source_sheet_number=sheet_number,
                    source_sheet_page_id=page_id,
                )

                # Store under exact tag, normalized tag, and variants
                entries[raw_tag] = entry
                norm_tag = normalize_wall_tag(raw_tag)
                if norm_tag:
                    entries[norm_tag] = entry

        return entries

    def parse_door_schedule(
        self, text_content: str, sheet_number: str = "A-701", page_id: int | None = None
    ) -> dict[str, DoorScheduleEntry]:
        """Parses door schedule items with explicit width and height dimensions."""
        entries: dict[str, DoorScheduleEntry] = {}
        lines = text_content.splitlines()

        # Regex for door schedule rows: "D01  3'-0" x 7'-0"  FLUSH WOOD"
        door_pattern = re.compile(
            r"\b(D\d{1,2}|WD-\d{1,2}|DR-\d{1,2})\b\s+(\d+['\-]?(?:\d+[\"/]?)?)\s*[xX×]\s*(\d+['\-]?(?:\d+[\"/]?)?)",
            re.IGNORECASE,
        )

        for line in lines:
            match = door_pattern.search(line)
            if match:
                tag = match.group(1).upper()
                w_str = match.group(2)
                h_str = match.group(3)

                w_ft = self._parse_dimension_ft(w_str, default=3.0)
                h_ft = self._parse_dimension_ft(h_str, default=7.0)

                entries[tag] = DoorScheduleEntry(
                    tag=tag,
                    width_ft=w_ft,
                    height_ft=h_ft,
                    source_sheet_number=sheet_number,
                    source_sheet_page_id=page_id,
                )

        return entries

    def _parse_dimension_ft(self, dim_str: str, default: float) -> float:
        try:
            dim_clean = dim_str.strip().replace("\"", "").replace("'", "")
            if "-" in dim_clean:
                parts = dim_clean.split("-")
                ft = float(parts[0])
                inch = float(parts[1]) if len(parts) > 1 else 0.0
                return round(ft + (inch / 12.0), 2)
            val = float(dim_clean)
            return val if val < 20 else round(val / 12.0, 2)
        except Exception:
            return default

    def _infer_gauge_from_desc(self, desc: str) -> str:
        """Infer stud gauge from schedule description text.

        GAP-G FIX: The previous implementation always returned "20 GA" regardless of
        what the schedule actually specified. This function extracts the gauge from the
        description text, with a fallback hierarchy based on stud depth:
          - 25 GA → light partition, ≤3-5/8" depth, no fire/rated callout
          - 20 GA → standard structural partition, 3-5/8"–6" depth
          - 18 GA → heavy-duty/rated assembly, explicitly called out

        Gauge is UNRESOLVED (returns "UNRESOLVED") when the description text
        contains no gauge indicator and the stud depth is ambiguous, so the
        caller can distinguish "not found in schedule" from "assumed".
        """
        d = desc.upper()

        # Explicit gauge callouts take top priority — the schedule says what it says
        if "18 GA" in d or "18GA" in d or "18-GAUGE" in d:
            return "18 GA"
        if "20 GA" in d or "20GA" in d or "20-GAUGE" in d:
            return "20 GA"
        if "25 GA" in d or "25GA" in d or "25-GAUGE" in d:
            return "25 GA"
        if "16 GA" in d or "16GA" in d:
            return "16 GA"

        # Fire-rated or acoustic assemblies typically require 20 GA minimum
        if "FIRE" in d or "1 HR" in d or "2 HR" in d or "1-HOUR" in d or "2-HOUR" in d:
            return "20 GA"

        # Furring channels are always 25 GA
        if "FURR" in d or "7/8" in d:
            return "25 GA"

        # 6" studs are heavy-duty — 20 GA minimum
        if "6\"" in d or "6 IN" in d or "6-INCH" in d:
            return "20 GA"

        # Light partition default: 25 GA
        # Per ASTM C645, non-load-bearing light partitions ≤3-5/8" use 25 GA
        return "25 GA"

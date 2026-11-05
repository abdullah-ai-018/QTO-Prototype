"""Extracts structured Door/Window Schedule tables from a schedule sheet's
vector table grid (PyMuPDF's `find_tables()`) — this reads real quantities
and per-type attributes directly from the drawing set's own schedule,
instead of relying on visually counting door/window symbols on the floor
plan (which the app deliberately does not trust for quantities — see
app/ai/validation_engine.py).

Table structure comes straight from the original vector PDF, so — like the
other fast-path PyMuPDF extraction in this codebase — this only works when
the schedule sheet has a real embedded table grid, not a scanned image.
"""

import re
from dataclasses import dataclass, field

_DOOR_CODE_RE = re.compile(r"^D-?\d{1,3}$", re.IGNORECASE)
_WINDOW_CODE_RE = re.compile(r"^W-?\d{1,3}$", re.IGNORECASE)
_SIZE_RE = re.compile(r"^\d+\s*[xX]\s*\d+")

# A table only counts as a real schedule grid if at least this many header
# cells match the item-code pattern — filters out small/partial table
# fragments `find_tables()` sometimes over-detects around the real one.
MIN_SCHEDULE_MATCHES = 2


@dataclass
class ParsedScheduleItem:
    schedule_type: str  # "door" | "window"
    item_code: str
    quantity: int
    attributes: dict = field(default_factory=dict)


def _guess_attribute_label(cell_text: str, used_labels: set[str]) -> str:
    lowered = cell_text.lower()
    if "glass" in lowered or "glazing" in lowered:
        label = "glazing"
    elif "frame" in lowered:
        label = "frame_material"
    elif _SIZE_RE.match(cell_text.strip()):
        label = "size"
    elif "measur" in lowered:
        label = "note"
    else:
        label = "detail"

    if label in used_labels:
        label = f"{label}_2"
    return label


def _parse_table(rows: list[list[str | None]], schedule_type: str, code_re: re.Pattern) -> list[ParsedScheduleItem]:
    if not rows:
        return []

    # Header row = whichever row has the most cells matching the item-code
    # pattern (schedule tables often have a blank label row above it).
    header_idx, header_matches = None, 0
    for idx, row in enumerate(rows):
        matches = sum(1 for c in row if c and code_re.match(c.strip()))
        if matches > header_matches:
            header_idx, header_matches = idx, matches
    if header_idx is None or header_matches < MIN_SCHEDULE_MATCHES:
        return []

    header = rows[header_idx]
    col_indices = [i for i, c in enumerate(header) if c and code_re.match(c.strip())]
    remaining_rows = rows[header_idx + 1 :]
    if not remaining_rows:
        return []

    # Quantity row = first remaining row where every matched column is
    # blank-or-integer, with at least one real number (i.e. a pure count row).
    qty_row = None
    for row in remaining_rows:
        cells = [row[i] if i < len(row) else None for i in col_indices]
        all_blank_or_int = all(c is None or c.strip() == "" or c.strip().isdigit() for c in cells)
        has_any_int = any(c and c.strip().isdigit() for c in cells)
        if all_blank_or_int and has_any_int:
            qty_row = row
            break
    if qty_row is None:
        return []

    attribute_rows = [r for r in remaining_rows if r is not qty_row]

    attributes_per_col: dict[int, dict] = {i: {} for i in col_indices}
    used_labels_per_col: dict[int, set[str]] = {i: set() for i in col_indices}
    for row in attribute_rows:
        for col_i in col_indices:
            cell = row[col_i] if col_i < len(row) else None
            if not cell or not cell.strip():
                continue
            label = _guess_attribute_label(cell, used_labels_per_col[col_i])
            attributes_per_col[col_i][label] = cell.strip().replace("\n", " ")
            used_labels_per_col[col_i].add(label)

    items: list[ParsedScheduleItem] = []
    for col_i in col_indices:
        code = header[col_i].strip().upper()
        qty_cell = qty_row[col_i] if col_i < len(qty_row) else None
        quantity = int(qty_cell.strip()) if qty_cell and qty_cell.strip().isdigit() else 0
        if quantity <= 0:
            continue
        items.append(
            ParsedScheduleItem(
                schedule_type=schedule_type,
                item_code=code,
                quantity=quantity,
                attributes=attributes_per_col[col_i],
            )
        )
    return items


def parse_schedule_pdf_page(pdf_path: str, page_number: int) -> list[ParsedScheduleItem]:
    """`page_number` is 1-indexed. Returns [] if the page has no usable
    table structure (scanned page, or no door/window schedule present).
    """
    try:
        import fitz
    except ImportError:
        return []

    items: list[ParsedScheduleItem] = []
    try:
        with fitz.open(pdf_path) as doc:
            page = doc.load_page(page_number - 1)
            for table in page.find_tables().tables:
                rows = table.extract()
                items.extend(_parse_table(rows, "door", _DOOR_CODE_RE))
                items.extend(_parse_table(rows, "window", _WINDOW_CODE_RE))
    except Exception as exc:
        print(f"[Protake] Schedule parser notice: {exc}")
        return []
    return items

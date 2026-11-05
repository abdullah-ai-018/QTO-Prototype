"""Scale measured from the drawing's own dimension annotations, rather
than read off its printed scale note.

A sheet's "SC 1/100" text states the scale the drawing was *authored* at.
It is not necessarily the scale the PDF in hand is *plotted* at: an export
resized to a different sheet size, or a detail placed at a different scale
than the title block claims, both leave that note stale. Trusting it is
then silently wrong in a way nothing downstream can catch — and the error
squares when pixels become areas.

Measured on a real commercial CAD sheet (A1, 181 DPI): the title block
said "SC 1/100", which converts to 0.046041 ft/px, but the sheet's own
gridline dimensions put A->D at 1,373 cm across 1,902 px = 0.023678 ft/px.
The printed note was off by 1.94x, so every area it produced was ~3.8x too
large — a 5 m2 kitchenette reported as 235 sqft (21.8 m2), and rooms
disappearing entirely through the real-world size gate.

What a human estimator does instead is measure a known dimension on the
drawing, which is exactly what this does: professional sheets carry a
gridline row (bubbles A, B, C, D...) with the bay dimension printed
between each adjacent pair, so the pixel distance between two bubbles has
its real-world length written right next to it.

The printed ratio is still used — as a coarse prior to resolve what unit
the dimension strings are in (500 could be mm, cm, or m), since a sheet
that is wrong about its scale is still nowhere near 20x wrong. The precise
value comes from the measurement.
"""

import re
import statistics
from dataclasses import dataclass

METERS_TO_FEET = 3.280839895013123

# A gridline bubble label is a single character (A-Z, or 1-9 on the other
# axis). Two-character labels exist on very large sheets (AA, AB) but are
# rare enough not to be worth the false matches admitting them would bring.
_BUBBLE_RE = re.compile(r"^[A-Z]$")

# Physical plausibility bounds for measured ft/px.
# At 300 DPI: 1/8"=1'-0" → 0.02667 ft/px; 1/4"=1'-0" → 0.05333 ft/px.
# Below 0.002 ft/px = 1 ft needs 500 px → implausible for construction docs.
# Above 0.20 ft/px = 1 ft needs 5 px → implausible for any readable drawing.
_MIN_PLAUSIBLE_FT_PER_PX = 0.002
_MAX_PLAUSIBLE_FT_PER_PX = 0.20

# A dimension string: digits, optionally with thousands separators
# ("1,373", "1.373", "3500", "12000") or a decimal part. Bare integers are the common case.
_DIMENSION_RE = re.compile(r"^\d{1,6}(?:[.,]\d{3})*(?:[.,]\d+)?$")

# Bubbles belong to the same gridline row when their centres sit within
# this share of the page height of each other.
_ROW_Y_TOLERANCE_RATIO = 0.01

# How far above/below the bubble row the dimension strip may sit. The
# dimension line is drawn just inboard of the bubbles; on the measured
# sheet the bubbles were at y=226px and the bay dimensions at y=378px on a
# 4233px page (3.6%).
_DIMENSION_BAND_RATIO = 0.08

# A pair contributes only if the dimension text sits comfortably inside the
# span it annotates, rather than near an endpoint where it could just as
# easily belong to the neighbouring bay.
_DIMENSION_INSET_RATIO = 0.15

# Candidate real-world units for a dimension string, as metres per unit.
_UNIT_CANDIDATES = {"mm": 0.001, "cm": 0.01, "m": 1.0}

# Consecutive bubbles must be at least this far apart (share of page width)
# to be a real structural bay rather than two labels of the same gridline.
_MIN_BAY_SPAN_RATIO = 0.02

# Enough independent bays must agree before overriding the printed ratio —
# one measurement could be a misread digit or a mismatched label.
_MIN_SAMPLES = 3

# Spread across the per-bay estimates, as a share of their median. Real
# bays measured on the same sheet agree closely; a scatter this wide means
# labels were matched to the wrong spans and the result is not trustworthy.
_MAX_RELATIVE_SPREAD = 0.15

# Only override the printed ratio when the measurement genuinely disagrees
# with it. Within this tolerance the two are saying the same thing, and the
# printed ratio is the more conventional value to record.
_MIN_DISAGREEMENT = 0.10


@dataclass
class MeasuredScale:
    ft_per_px: float
    unit: str
    samples: int
    relative_spread: float


_ELECTRICAL_OR_ANNOTATION_RE = re.compile(
    r"""(#|\b(AWG|VOLT|V|AMP|A|WATT|W|KVA|HP|CIRCUIT|CKT|PNL|PANEL|BREAKER|CONDUIT|WIRE|MC|FLEX|J-BOX|HVAC|CFM|TON|BTU|PPM|RMS|HZ)\b)""",
    re.IGNORECASE,
)


def _parse_dimension(text: str) -> float | None:
    """The numeric value of a dimension string, or None if it isn't one.

    Separators are ambiguous across locales ("1,373" is one thousand three
    hundred seventy-three in one convention and 1.373 in another), so a
    group of exactly three digits after a separator is read as a thousands
    group — the reading that makes a floor-plan bay dimension plausible in
    every unit this considers.
    """
    clean = text.strip()
    if _ELECTRICAL_OR_ANNOTATION_RE.search(clean):
        return None
    if not _DIMENSION_RE.match(clean):
        return None
    cleaned = re.sub(r"[.,](\d{3})\b", r"\1", clean)
    cleaned = cleaned.replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    # Reject values < 10 (which are almost certainly circuit, room numbers, or wire counts, not structural bay dimensions)
    if value < 10.0:
        return None
    return value if value > 0 else None


def _token_box(token) -> tuple[float, float, float, float]:
    xs = [p[0] for p in token.bbox_px]
    ys = [p[1] for p in token.bbox_px]
    return min(xs), min(ys), max(xs), max(ys)


def measure_scale_from_dimensions(
    tokens: list,
    image_w: int,
    image_h: int,
    prior_ft_per_px: float | None = None,
) -> MeasuredScale | None:
    """Feet-per-pixel measured from gridline bubbles and the bay dimensions
    printed between them, or None when the sheet doesn't carry a readable
    gridline row.

    `prior_ft_per_px` (the printed scale note's value, when there is one)
    only selects which unit the dimension strings are in — it never enters
    the returned magnitude.
    """
    if not tokens or image_w <= 0 or image_h <= 0:
        return None

    bubbles: list[tuple[float, float]] = []
    dimensions: list[tuple[float, float, float]] = []  # cx, cy, value
    for token in tokens:
        text = (token.text or "").strip()
        if not text:
            continue
        x0, y0, x1, y1 = _token_box(token)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if _BUBBLE_RE.match(text.upper()):
            bubbles.append((cx, cy))
            continue
        value = _parse_dimension(text)
        if value is not None:
            dimensions.append((cx, cy, value))

    if len(bubbles) < 2 or not dimensions:
        return None

    rows = _gridline_bubble_rows(bubbles, image_w, image_h)
    if not rows:
        return None

    band = image_h * _DIMENSION_BAND_RATIO
    min_span = image_w * _MIN_BAY_SPAN_RATIO

    best: MeasuredScale | None = None
    for row in rows:
        row_y = statistics.median([y for _, y in row])

        # A dimension strip is several stacked rows, not one: an overall
        # dimension over the whole span, the structural bay dimensions
        # under it, then finer sub-dimensions (openings, wall offsets)
        # under those. Matching against all of them at once finds several
        # values inside every bay and can resolve none of them, so each
        # row is tried on its own and the most self-consistent one wins.
        nearby = [(cx, cy, v) for cx, cy, v in dimensions if abs(cy - row_y) <= band]
        for strip in _cluster_dimension_rows(nearby, image_h):
            spans: list[tuple[float, float]] = []  # px_gap, printed_value
            for (ax, _), (bx, _) in zip(row, row[1:]):
                gap = bx - ax
                if gap < min_span:
                    continue
                inset = gap * _DIMENSION_INSET_RATIO
                inside = [value for cx, value in strip if ax + inset <= cx <= bx - inset]
                if len(inside) != 1:
                    # Zero means this bay's dimension wasn't read in this
                    # row; more than one means this row is finer-grained
                    # than the bay and carries no single value for it. The
                    # gutter between two plans on one sheet lands here too,
                    # which is what keeps it from being measured as a bay.
                    continue
                spans.append((gap, inside[0]))

            if len(spans) < _MIN_SAMPLES:
                continue

            unit = _choose_unit(spans, prior_ft_per_px)
            metres_per_unit = _UNIT_CANDIDATES[unit]
            estimates = [(value * metres_per_unit * METERS_TO_FEET) / gap for gap, value in spans]

            # One bad pairing must not veto an otherwise unanimous set. On a
            # two-plan sheet the bubble run spans the gutter between the
            # plans, and that non-bay does land next to a dimension
            # belonging to the next plan — a single wildly-off estimate
            # among six agreeing ones. Real bays cluster tightly (measured:
            # 0.02301, 0.02291 repeated), so the median is already the
            # right answer and outliers are simply dropped rather than
            # being allowed to fail the consistency check.
            median = statistics.median(estimates)
            if median <= 0:
                continue
            inliers = [e for e in estimates if abs(e - median) / median <= _MAX_RELATIVE_SPREAD]
            if len(inliers) < _MIN_SAMPLES:
                continue

            median = statistics.median(inliers)
            spread = (max(inliers) - min(inliers)) / median
            if best is None or spread < best.relative_spread:
                best = MeasuredScale(
                    ft_per_px=median, unit=unit, samples=len(inliers), relative_spread=spread
                )

    # Reject physically impossible results — electrical circuit labels, schedule
    # numbers, or other non-bay text can look like bubbles+dimensions and
    # produce ft/px values orders of magnitude outside any real drawing scale.
    if best is not None and not (_MIN_PLAUSIBLE_FT_PER_PX <= best.ft_per_px <= _MAX_PLAUSIBLE_FT_PER_PX):
        return None
    return best


def _cluster_dimension_rows(
    dimensions: list[tuple[float, float, float]], image_h: int
) -> list[list[tuple[float, float]]]:
    """Split dimension tokens into the horizontal rows they were printed
    in, each returned as (x_centre, value) sorted left to right.
    """
    tolerance = image_h * _ROW_Y_TOLERANCE_RATIO
    rows: list[list[tuple[float, float, float]]] = []
    for item in sorted(dimensions, key=lambda d: d[1]):
        for row in rows:
            if abs(item[1] - statistics.median([r[1] for r in row])) <= tolerance:
                row.append(item)
                break
        else:
            rows.append([item])
    return [sorted([(cx, v) for cx, _, v in row]) for row in rows]


def _gridline_bubble_rows(
    bubbles: list[tuple[float, float]], image_w: int, image_h: int
) -> list[list[tuple[float, float]]]:
    """Every distinct structural gridline row found (bubbles A, B, C, D...
    on one shared baseline), each left to right, widest first.

    A sheet with two floor plans side by side prints two such rows — one
    per plan — and they are not guaranteed to share a baseline: measured
    on a real sheet, one page's two plans sat close enough in y to fall
    inside one row's tolerance and merge (6 valid bay spans across both),
    while another page's two plans were offset by ~55px, just outside that
    tolerance, and were previously only ever tried one at a time — with
    only 4 bubbles (3 bay gaps) per plan, a single unmatched gap in
    whichever row happened to be picked was enough to fall below
    _MIN_SAMPLES and report no measurement at all, when the other plan's
    row alone would have measured fine. Returning every row candidate and
    trying each (see measure_scale_from_dimensions) fixes that without
    having to guess which plan's row is "the" one in advance.

    Picking simply the most populated horizontal row does not work: a floor
    plan is littered with other single letters, and on the measured sheet
    the densest row by count (27 labels) was the row of "A B C D E" room
    finish-tag boxes drawn *inside* the rooms, spaced ~22px apart, not the
    8 gridline bubbles spanning the sheet. Those clusters are excluded by
    requiring bubbles to be a real structural bay apart, and the surviving
    row that spans the most of the sheet is taken — a gridline row runs the
    full width of the plan by definition, while any incidental alignment of
    unrelated letters does not.

    A sheet carrying two floor plans side by side prints the same A/B/C/D
    labels twice on one row; both are kept, and the pair straddling the
    gutter between plans is rejected later by its dimension strip holding
    no single matching value.
    """
    tolerance = image_h * _ROW_Y_TOLERANCE_RATIO
    min_gap = image_w * _MIN_BAY_SPAN_RATIO

    candidates: list[list[tuple[float, float]]] = []
    seen_signatures: set[tuple[int, int]] = set()
    for _, anchor_y in bubbles:
        row = sorted(
            ((x, y) for x, y in bubbles if abs(y - anchor_y) <= tolerance),
            key=lambda p: p[0],
        )
        # Collapse tight clusters (finish tags, legend keys) to one entry so
        # they can never masquerade as a run of bays.
        spread: list[tuple[float, float]] = []
        for point in row:
            if not spread or point[0] - spread[-1][0] >= min_gap:
                spread.append(point)
        if len(spread) < _MIN_SAMPLES:
            continue

        # Different anchors within the same physical row produce the same
        # (or near-identical) point set — dedup so that row isn't tried
        # over and over.
        signature = (round(spread[0][0]), round(spread[0][1]))
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        candidates.append(spread)

    candidates.sort(key=lambda row: row[-1][0] - row[0][0], reverse=True)
    return candidates


def _choose_unit(spans: list[tuple[float, float]], prior_ft_per_px: float | None) -> str:
    """Which real-world unit the dimension strings are written in.

    Without a prior this defaults to centimetres, the common convention for
    metric architectural plans (and the one measured on the real sheet).
    With one, the unit whose implied scale lands nearest the printed note
    wins: the note can be wrong about the exact plot scale, but not by the
    10x-1000x that separates millimetres from metres.
    """
    if prior_ft_per_px is None or prior_ft_per_px <= 0:
        return "cm"

    best_unit, best_error = "cm", float("inf")
    for unit, metres_per_unit in _UNIT_CANDIDATES.items():
        estimates = [(value * metres_per_unit * METERS_TO_FEET) / gap for gap, value in spans]
        median = statistics.median(estimates)
        if median <= 0:
            continue
        error = abs(math_log_ratio(median, prior_ft_per_px))
        if error < best_error:
            best_unit, best_error = unit, error
    return best_unit


def math_log_ratio(a: float, b: float) -> float:
    import math

    return math.log(a / b)


def disagrees_with_prior(measured_ft_per_px: float, prior_ft_per_px: float) -> bool:
    """Whether a measurement is far enough from the printed scale note to
    be worth overriding it (see _MIN_DISAGREEMENT).
    """
    if prior_ft_per_px <= 0:
        return True
    return abs(measured_ft_per_px - prior_ft_per_px) / prior_ft_per_px > _MIN_DISAGREEMENT

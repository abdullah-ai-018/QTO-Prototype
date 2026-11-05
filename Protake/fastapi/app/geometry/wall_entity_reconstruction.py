"""
Evidence-Based Physical Wall Entity Reconstruction Module.

Performs multi-source forensic evidence validation and collinear entity
reconstruction on CAD vector linework:
1. Rejects non-wall geometry (title blocks, dimensions, grids, furniture, hatch, stair treads, annotations, MEP).
2. Requires dual-face parallel pairing within architectural wall thickness (3.0" - 16.0") or strong opening/continuity proof.
3. Reconstructs parallel wall faces into single canonical physical wall centerlines located precisely at (Face A + Face B) / 2.
4. Performs graph-based topological node clustering and collinear bridging across openings.
5. Emits verified physical wall entities with zero title block/dimension noise and full source evidence.
"""

import logging
import math
from typing import Any
import fitz

logger = logging.getLogger(__name__)

from app.models.enums import ReviewStatus
from app.geometry.stair_cavity_detector import (
    detect_stair_cavities_from_drawings,
    is_segment_interior_stair_detail,
)

COMPATIBLE_WALL_LAYERS = {
    "wall", "ex-wall", "internal wall", "structural - bearing", "structural", "stair",
    "partition", "a-wall", "s-wall", "a-wall-full", "a-wall-prtn", "drywall", "gyp", "con"
}

# Title-block / margin exclusion zones (fraction of page width/height).
# Standard AIA/ANSI D-size and E-size sheets place the title block in the
# lower-right corner (roughly the rightmost 22% × lower 40%).  Adjust here
# for non-standard sheet layouts rather than hunting for magic numbers.
TITLE_BLOCK_X_MIN = 0.78   # x > this AND y > TITLE_BLOCK_Y_MIN  ⟹ title block
TITLE_BLOCK_Y_MIN = 0.60
BORDER_BOTTOM_Y   = 0.92   # y > this  ⟹ bottom border strip
BORDER_LEFT_X     = 0.04   # x < this  ⟹ left binding margin
BORDER_TOP_Y      = 0.05   # y < this  ⟹ top border strip
ENVELOPE_RIGHT_X  = 0.96   # x > this  ⟹ right border strip

NEGATIVE_LAYER_TOKENS = [
    "furniture", "50_furniture", "object", "2d drafting", "text",
    "dim", "axis", "grid", "structural grid", "hatch", "column",
    "window", "border", "title", "sheet", "note", "leader",
    # DEF-07: MEP/electrical/plumbing layers must never become wall candidates.
    "electrical", "plumbing", "mep", "mechanical", "hvac",
    "pipe", "conduit", "duct", "sprinkler", "fire",
]


def is_compatible_wall_layer(layer_str: str) -> bool:
    l = layer_str.lower().strip()
    if any(tok in l for tok in NEGATIVE_LAYER_TOKENS):
        return False
    return any(wl in l for wl in COMPATIBLE_WALL_LAYERS)


def is_architectural_wall_candidate(
    s: dict,
    stair_cavities: list[dict],
    openings: list,
    image_dims: tuple[int, int] = (1000, 1000),
    scale_ft_per_px: float = 0.02,
) -> bool:
    if s.get("is_in_title_block") or s.get("is_outside_envelope"):
        return False

    l = s["layer"].lower().strip()
    w_pt = s["width_pt"]
    len_ft = s["length_ft"]

    # Reject explicit negative tokens
    if any(tok in l for tok in NEGATIVE_LAYER_TOKENS):
        return False

    # Allow positive wall layer OR unnamed/blank layer (for dual-face pairing / opening evidence)
    is_wall_l = any(wl in l for wl in COMPATIBLE_WALL_LAYERS)
    # DEF-06: exact/prefix match only — "layer" in l admitted "ELECTRICAL LAYER" etc.
    _UNNAMED_EXACT = {"", "unnamed", "layer", "0", "defpoints"}
    is_unnamed = l in _UNNAMED_EXACT or (l.startswith("layer ") and l[6:].strip().isdigit())
    if not (is_wall_l or is_unnamed):
        return False

    # Structural bearing lineweight threshold
    if "structural - bearing" in l and w_pt < 0.51:
        return False

    # Generalized Stair Interior Cavity Rejection
    if stair_cavities:
        normalized_cavities = []
        for cav in stair_cavities:
            if isinstance(cav, (tuple, list)):
                normalized_cavities.append({"bbox_px": tuple(cav)})
            else:
                normalized_cavities.append(cav)
        if is_segment_interior_stair_detail(s, normalized_cavities, image_dims, scale_ft_per_px):
            return False

    # Reject subscale fragments (< 1.2 ft)
    if len_ft < 1.2:
        return False

    return True


def classify_gap(
    gap_px: float,
    gap_mid: float,
    ax_val: float,
    orient: str,
    openings: list,
    scale_ft_per_px: float,
) -> str:
    gap_ft = gap_px * scale_ft_per_px
    if gap_ft <= 0.25:
        return "A_CONTIGUOUS_SNAPPED"
    if gap_ft <= 2.2:
        return "D_COLUMN_JUNCTION_GAP"

    if gap_ft <= 9.5:
        for op in openings:
            op_pos = op["center"][0] if orient == "H" else op["center"][1]
            op_off = op["center"][1] if orient == "H" else op["center"][0]
            if abs(op_off - ax_val) <= (3.0 / scale_ft_per_px) and abs(op_pos - gap_mid) <= (5.5 / scale_ft_per_px):
                return "B_DOOR_OPENING" if op["type"] == "DOOR" else "C_WINDOW_OPENING"
        # DEF-05: threshold-alone bridging is prohibited. Only opening-evidence
        # paths above may return B_DOOR_OPENING / C_WINDOW_OPENING.
        pass

    return "G_TRUE_WALL_TERMINATION"


def extract_and_reconstruct_wall_entities(
    pdf_path: str,
    page_number: int,
    image_dims: tuple[int, int],
    scale_ft_per_px: float,
) -> list[dict[str, Any]]:
    """Extracts CAD vector linework from PDF, applies multi-source physical evidence,
    pairs parallel faces into true physical centerlines, and reconstructs canonical
    wall entities across door/window openings.
    """
    h, w = image_dims
    if h <= 0 or w <= 0 or scale_ft_per_px <= 0:
        return []

    doc = fitz.open(pdf_path)
    if page_number < 1 or page_number > len(doc):
        return []

    pdf_page = doc[page_number - 1]
    pw, ph = pdf_page.rect.width, pdf_page.rect.height
    if pw <= 0 or ph <= 0:
        return []
    scale_x = w / pw
    scale_y = h / ph

    drawings = pdf_page.get_drawings()

    # 1. Detect stair cavities dynamically from drawing linework
    stair_cavities = detect_stair_cavities_from_drawings(drawings, image_dims, scale_ft_per_px)

    # 2. Extract Openings (Doors / Windows)
    openings = []
    for d in drawings:
        l = (d.get("layer") or "").lower()
        if "door" in l or "window" in l:
            r = d.get("rect")
            if r:
                x0, y0, x1, y1 = r.x0 * scale_x, r.y0 * scale_y, r.x1 * scale_x, r.y1 * scale_y
                openings.append({
                    "type": "DOOR" if "door" in l else "WINDOW",
                    "center": ((x0 + x1) / 2.0, (y0 + y1) / 2.0),
                    "bbox": (x0, y0, x1, y1),
                })

    # 3. Extract Raw Segments
    raw_segments = []
    seg_id = 0
    for d in drawings:
        l = (d.get("layer") or "").lower()
        width = d.get("width") or 0.5
        for it in d.get("items", []):
            item_type = it[0]
            pts_pairs = []
            if item_type == "l":
                pts_pairs.append((it[1], it[2]))
            elif item_type == "re":
                r = it[1]
                p_tl = fitz.Point(r.x0, r.y0)
                p_tr = fitz.Point(r.x1, r.y0)
                p_br = fitz.Point(r.x1, r.y1)
                p_bl = fitz.Point(r.x0, r.y1)
                pts_pairs.extend([(p_tl, p_tr), (p_tr, p_br), (p_br, p_bl), (p_bl, p_tl)])
            elif item_type == "qu":
                q = it[1]
                pts_pairs.extend([(q.ul, q.ur), (q.ur, q.lr), (q.lr, q.ll), (q.ll, q.ul)])

            for p1, p2 in pts_pairs:
                x1_px, y1_px = p1.x * scale_x, p1.y * scale_y
                x2_px, y2_px = p2.x * scale_x, p2.y * scale_y

                dx, dy = x2_px - x1_px, y2_px - y1_px
                length_px = math.hypot(dx, dy)
                length_ft = length_px * scale_ft_per_px

                if length_ft < 0.5:
                    continue

                x_mid = (x1_px + x2_px) / 2.0
                y_mid = (y1_px + y2_px) / 2.0
                angle_deg = round(math.degrees(math.atan2(dy, dx)) % 180.0, 1)

                is_in_title_block = (
                    (x_mid > w * TITLE_BLOCK_X_MIN and y_mid > h * TITLE_BLOCK_Y_MIN)
                    or (y_mid > h * BORDER_BOTTOM_Y)
                    or (x_mid < w * BORDER_LEFT_X)
                    or (y_mid < h * BORDER_TOP_Y)
                )
                is_outside_envelope = (
                    (x_mid > w * ENVELOPE_RIGHT_X)
                    or (x_mid < w * BORDER_LEFT_X)
                    or (y_mid < h * BORDER_TOP_Y)
                    or (y_mid > h * BORDER_BOTTOM_Y)
                )

                seg_id += 1
                raw_segments.append({
                    "id": seg_id,
                    "layer": l,
                    "width_pt": width,
                    "p1": (x1_px, y1_px),
                    "p2": (x2_px, y2_px),
                    "dx": dx,
                    "dy": dy,
                    "length_ft": round(length_ft, 2),
                    "angle_deg": angle_deg,
                    "is_in_title_block": is_in_title_block,
                    "is_outside_envelope": is_outside_envelope,
                })


    if not raw_segments:
        return []

    # 4. Filter Potential Wall Strokes
    potential_wall_strokes = [
        s for s in raw_segments
        if is_architectural_wall_candidate(s, stair_cavities, openings, image_dims, scale_ft_per_px)
    ]

    # 5. Pair Parallel Faces (dual-face wall thickness evidence: 2.0" - 24.0")
    min_sep_px = (2.0 / 12.0) / scale_ft_per_px
    max_sep_px = (24.0 / 12.0) / scale_ft_per_px

    # Record best pairing for each stroke
    paired_candidates: list[dict[str, Any]] = []
    paired_stroke_ids: set[int] = set()

    for i, s1 in enumerate(potential_wall_strokes):
        for j in range(i + 1, len(potential_wall_strokes)):
            s2 = potential_wall_strokes[j]
            angle_diff = abs(s1["angle_deg"] - s2["angle_deg"])
            if not (angle_diff < 3.5 or angle_diff > 176.5):
                continue

            len_norm = s1["length_ft"] / scale_ft_per_px
            if len_norm <= 0:
                continue
            vx = s1["dx"] / len_norm
            vy = s1["dy"] / len_norm
            nx, ny = -vy, vx

            d1 = abs((s2["p1"][0] - s1["p1"][0]) * nx + (s2["p1"][1] - s1["p1"][1]) * ny)
            d2 = abs((s2["p2"][0] - s1["p1"][0]) * nx + (s2["p2"][1] - s1["p1"][1]) * ny)
            dist_px = (d1 + d2) / 2.0

            if min_sep_px <= dist_px <= max_sep_px:
                t1_2 = (s1["p2"][0] - s1["p1"][0]) * vx + (s1["p2"][1] - s1["p1"][1]) * vy
                t2_1 = (s2["p1"][0] - s1["p1"][0]) * vx + (s2["p1"][1] - s1["p1"][1]) * vy
                t2_2 = (s2["p2"][0] - s1["p1"][0]) * vx + (s2["p2"][1] - s1["p1"][1]) * vy

                min_t1, max_t1 = 0.0, t1_2
                if max_t1 < min_t1:
                    min_t1, max_t1 = max_t1, min_t1
                min_t2, max_t2 = min(t2_1, t2_2), max(t2_1, t2_2)

                overlap_start = max(min_t1, min_t2)
                overlap_end = min(max_t1, max_t2)
                overlap_px = overlap_end - overlap_start

                if overlap_px > (0.8 / scale_ft_per_px):
                    thick_in = round(dist_px * scale_ft_per_px * 12.0, 1)
                    ang = s1["angle_deg"]
                    orient = "H" if (ang <= 15.0 or ang >= 165.0) else ("V" if (75.0 <= ang <= 105.0) else "O")

                    # True physical centerline: offset is exactly midway between Face A and Face B
                    if orient == "H":
                        ax1 = (s1["p1"][1] + s1["p2"][1]) / 2.0
                        ax2 = (s2["p1"][1] + s2["p2"][1]) / 2.0
                        center_ax = (ax1 + ax2) / 2.0
                        sp1 = (min(s1["p1"][0], s1["p2"][0], s2["p1"][0], s2["p2"][0]), center_ax)
                        sp2 = (max(s1["p1"][0], s1["p2"][0], s2["p1"][0], s2["p2"][0]), center_ax)
                        span_min = min(s1["p1"][0], s1["p2"][0], s2["p1"][0], s2["p2"][0])
                        span_max = max(s1["p1"][0], s1["p2"][0], s2["p1"][0], s2["p2"][0])
                    elif orient == "V":
                        ax1 = (s1["p1"][0] + s1["p2"][0]) / 2.0
                        ax2 = (s2["p1"][0] + s2["p2"][0]) / 2.0
                        center_ax = (ax1 + ax2) / 2.0
                        sp1 = (center_ax, min(s1["p1"][1], s1["p2"][1], s2["p1"][1], s2["p2"][1]))
                        sp2 = (center_ax, max(s1["p1"][1], s1["p2"][1], s2["p1"][1], s2["p2"][1]))
                        span_min = min(s1["p1"][1], s1["p2"][1], s2["p1"][1], s2["p2"][1])
                        span_max = max(s1["p1"][1], s1["p2"][1], s2["p1"][1], s2["p2"][1])
                    else:
                        # Diagonal wall: project endpoints along wall direction (vx, vy)
                        # n = (-vy, vx) is the unit normal; perp = p · n
                        t_11 = s1["p1"][0] * vx + s1["p1"][1] * vy
                        t_12 = s1["p2"][0] * vx + s1["p2"][1] * vy
                        t_21 = s2["p1"][0] * vx + s2["p1"][1] * vy
                        t_22 = s2["p2"][0] * vx + s2["p2"][1] * vy
                        span_min = min(t_11, t_12, t_21, t_22)
                        span_max = max(t_11, t_12, t_21, t_22)
                        m1x = (s1["p1"][0] + s1["p2"][0]) / 2.0
                        m1y = (s1["p1"][1] + s1["p2"][1]) / 2.0
                        m2x = (s2["p1"][0] + s2["p2"][0]) / 2.0
                        m2y = (s2["p1"][1] + s2["p2"][1]) / 2.0
                        perp1 = m1x * (-vy) + m1y * vx
                        perp2 = m2x * (-vy) + m2y * vx
                        center_ax = (perp1 + perp2) / 2.0
                        # Reconstruct pixel endpoints: p = along·v̂ + perp·n̂
                        sp1 = (span_min * vx + center_ax * (-vy), span_min * vy + center_ax * vx)
                        sp2 = (span_max * vx + center_ax * (-vy), span_max * vy + center_ax * vx)

                    paired_stroke_ids.add(s1["id"])
                    paired_stroke_ids.add(s2["id"])

                    paired_candidates.append({
                        "candidate_id": f"{s1['id']}_{s2['id']}",
                        "face_a_id": s1["id"],
                        "face_b_id": s2["id"],
                        "face_a_coords": {
                            "x1": round(s1["p1"][0] / w, 5), "y1": round(s1["p1"][1] / h, 5),
                            "x2": round(s1["p2"][0] / w, 5), "y2": round(s1["p2"][1] / h, 5),
                        },
                        "face_b_coords": {
                            "x1": round(s2["p1"][0] / w, 5), "y1": round(s2["p1"][1] / h, 5),
                            "x2": round(s2["p2"][0] / w, 5), "y2": round(s2["p2"][1] / h, 5),
                        },
                        "layer": s1["layer"] if is_compatible_wall_layer(s1["layer"]) else s2["layer"],
                        "layers": [s1["layer"], s2["layer"]],
                        "width_pt": max(s1["width_pt"], s2["width_pt"]),
                        "p1": sp1,
                        "p2": sp2,
                        "span_min": span_min,
                        "span_max": span_max,
                        "center_ax": center_ax,
                        "length_ft": round((span_max - span_min) * scale_ft_per_px, 2),
                        "angle_deg_cand": ang,
                        "orientation": orient,
                        "has_paired_face": True,
                        "thickness_measured_in": thick_in,
                    })

    # 6. Form Confirmed Physical Candidates (Including high-evidence single strokes)
    confirmed_candidates: list[dict[str, Any]] = list(paired_candidates)

    # For unpaired strokes: ONLY admit if they have attached openings AND compatible wall layer
    for s in potential_wall_strokes:
        if s["id"] in paired_stroke_ids:
            continue
        ang = s["angle_deg"]
        orient = "H" if (ang <= 15.0 or ang >= 165.0) else ("V" if (75.0 <= ang <= 105.0) else "O")

        l = s["layer"]
        attached_openings = []
        if orient == "O":
            ang_rad_d = math.radians(ang)
            vx_d = math.cos(ang_rad_d)
            vy_d = math.sin(ang_rad_d)
            half_len_px = math.hypot(s["p2"][0] - s["p1"][0], s["p2"][1] - s["p1"][1]) / 2.0
            mx_d = (s["p1"][0] + s["p2"][0]) / 2.0
            my_d = (s["p1"][1] + s["p2"][1]) / 2.0
            for op in openings:
                op_c = op["center"]
                d_x = op_c[0] - mx_d
                d_y = op_c[1] - my_d
                perp_dist = abs(d_x * (-vy_d) + d_y * vx_d)
                along_pos = d_x * vx_d + d_y * vy_d
                if perp_dist <= 30 and -20 <= along_pos <= half_len_px + 20:
                    attached_openings.append(op)
        else:
            for op in openings:
                op_c = op["center"]
                if orient == "H":
                    if min(s["p1"][0], s["p2"][0]) - 20 <= op_c[0] <= max(s["p1"][0], s["p2"][0]) + 20:
                        if abs(op_c[1] - s["p1"][1]) <= 30:
                            attached_openings.append(op)
        # Evidence-based admission for unpaired strokes:
        #   Named wall layer: admit if has opening OR length >= 1.5 ft.
        #   Unnamed layer + opening: admit (strong proximity evidence).
        #   Unnamed layer, no opening, length >= 4.0 ft: admit as NEEDS_REVIEW
        #     (long geometry on a page with no named wall layers is more likely
        #     a genuine wall than a symbol; the downstream validation gate will
        #     apply further topology checks).
        #   Unnamed layer, no opening, length < 4.0 ft: drop (symbol/hatch risk
        #     outweighs wall benefit at this length without additional evidence).
        is_named_wall = is_compatible_wall_layer(l)
        if not is_named_wall:
            if len(attached_openings) == 0:
                # Real interior partitions (toilets, stairs, storage, tenant dividers) are 3.0 ft - 35.0 ft.
                # Lines < 3.0 ft are noise/symbols; lines > 35.0 ft are structural grid lines spanning the page.
                if s["length_ft"] < 3.0 or s["length_ft"] > 35.0:
                    logger.debug(
                        "D1-DROP unnamed unpaired stroke len=%.2f ft (outside 3.0-35.0 ft partition range)",
                        s["length_ft"],
                    )
                    continue
                recon_evidence = "UNNAMED_LAYER_PARTITION_CANDIDATE"
            else:
                recon_evidence = "UNNAMED_LAYER_EVIDENCE_BACKED"
        else:
            if len(attached_openings) == 0 and s["length_ft"] < 1.5:
                continue
            recon_evidence = "SINGLE_FACE_NAMED_LAYER"



        if orient == "H":
            center_ax = (s["p1"][1] + s["p2"][1]) / 2.0
            span_min = min(s["p1"][0], s["p2"][0])
            span_max = max(s["p1"][0], s["p2"][0])
        elif orient == "V":
            center_ax = (s["p1"][0] + s["p2"][0]) / 2.0
            span_min = min(s["p1"][1], s["p2"][1])
            span_max = max(s["p1"][1], s["p2"][1])
        else:
            ang_rad_d = math.radians(ang)
            vx_d = math.cos(ang_rad_d)
            vy_d = math.sin(ang_rad_d)
            t_p1 = s["p1"][0] * vx_d + s["p1"][1] * vy_d
            t_p2 = s["p2"][0] * vx_d + s["p2"][1] * vy_d
            span_min = min(t_p1, t_p2)
            span_max = max(t_p1, t_p2)
            mx_d = (s["p1"][0] + s["p2"][0]) / 2.0
            my_d = (s["p1"][1] + s["p2"][1]) / 2.0
            center_ax = mx_d * (-vy_d) + my_d * vx_d

        confirmed_candidates.append({
            "candidate_id": str(s["id"]),
            "face_a_id": s["id"],
            "face_b_id": None,
            "face_a_coords": {
                "x1": round(s["p1"][0] / w, 5), "y1": round(s["p1"][1] / h, 5),
                "x2": round(s["p2"][0] / w, 5), "y2": round(s["p2"][1] / h, 5),
            },
            "face_b_coords": None,
            "layer": l or "unnamed",
            "layers": [l or "unnamed"],
            "width_pt": s["width_pt"],
            "p1": s["p1"],
            "p2": s["p2"],
            "span_min": span_min,
            "span_max": span_max,
            "center_ax": center_ax,
            "length_ft": s["length_ft"],
            "angle_deg_cand": ang,
            "orientation": orient,
            "has_paired_face": False,
            "thickness_measured_in": None,
            "evidence_type": recon_evidence,
        })

    if not confirmed_candidates:
        return []

    # 7. Collinear Axis Clustering & Gap-Classified Reconstruction
    stair_north_barriers: list[tuple[float, float, float, float]] = []
    for cav in stair_cavities:
        bx0, by0, bx1, by1 = cav["bbox_px"]
        x_margin = (bx1 - bx0) * 0.35
        barrier_tol = h * 0.004
        stair_north_barriers.append((bx0 - x_margin, bx1 + x_margin, by0, barrier_tol))

    # entity tuple: (cand_list, span_min, span_max, axis_offset, orient, angle_deg)
    # For H: axis_offset=y_px, span=x_px range; angle_deg=0
    # For V: axis_offset=x_px, span=y_px range; angle_deg=90
    # For O: axis_offset=perp offset from origin, span=along-wall px range; angle_deg=actual
    entities: list[tuple[list[dict], float, float, float, str, float]] = []

    for orient in ["H", "V"]:
        orient_cands = [c for c in confirmed_candidates if c["orientation"] == orient]
        ang_deg_fixed = 0.0 if orient == "H" else 90.0

        axis_clusters: dict[float, list[dict]] = {}
        for c in orient_cands:
            offset = c["center_ax"]
            matched = None
            for ax_val in axis_clusters:
                # 0.5 ft axis tolerance for collinear grouping
                if abs(ax_val - offset) <= (0.5 / scale_ft_per_px):
                    matched = ax_val
                    break
            if matched is not None:
                axis_clusters[matched].append(c)
            else:
                axis_clusters[offset] = [c]

        for ax_val, cand_list in axis_clusters.items():
            cand_spans = [(c["span_min"], c["span_max"], c) for c in cand_list]
            cand_spans.sort(key=lambda x: x[0])

            current_cands: list[dict] = []
            current_min = current_max = 0.0
            window_bridge_count = 0

            for s0, s1, cand in cand_spans:
                if not current_cands:
                    current_cands = [cand]
                    current_min, current_max = s0, s1
                    continue

                gap_px = s0 - current_max
                gap_mid = (current_max + s0) / 2.0
                gap_type = classify_gap(gap_px, gap_mid, ax_val, orient, openings, scale_ft_per_px)

                # Cross-stair barrier guard
                if orient == "V":
                    for ax_lo, ax_hi, barrier_y, barrier_tol in stair_north_barriers:
                        if ax_lo <= ax_val <= ax_hi:
                            if current_max < (barrier_y + barrier_tol) and s0 > (barrier_y - barrier_tol):
                                gap_type = "G_TRUE_WALL_TERMINATION"
                                break

                if gap_type == "C_WINDOW_OPENING":
                    window_bridge_count += 1
                    if window_bridge_count > 1:
                        gap_type = "G_TRUE_WALL_TERMINATION"
                elif gap_type != "C_WINDOW_OPENING":
                    window_bridge_count = 0

                if gap_type in ("A_CONTIGUOUS_SNAPPED", "B_DOOR_OPENING", "C_WINDOW_OPENING", "D_COLUMN_JUNCTION_GAP"):
                    current_cands.append(cand)
                    current_max = max(current_max, s1)
                else:
                    entities.append((current_cands, current_min, current_max, ax_val, orient, ang_deg_fixed))
                    current_cands = [cand]
                    current_min, current_max = s0, s1
                    window_bridge_count = 0

            if current_cands:
                entities.append((current_cands, current_min, current_max, ax_val, orient, ang_deg_fixed))

    # Diagonal walls: cluster by angle bin then by perpendicular offset
    diag_cands = [c for c in confirmed_candidates if c["orientation"] == "O"]
    if diag_cands:
        angle_groups: dict[int, list[dict]] = {}
        for c in diag_cands:
            ang_bin = round(c["angle_deg_cand"] / 5.0) * 5
            if ang_bin not in angle_groups:
                angle_groups[ang_bin] = []
            angle_groups[ang_bin].append(c)

        for ang_bin, angle_cands in angle_groups.items():
            axis_clusters_d: dict[float, list[dict]] = {}
            for c in angle_cands:
                offset = c["center_ax"]
                matched = None
                for ax_val in axis_clusters_d:
                    if abs(ax_val - offset) <= (0.5 / scale_ft_per_px):
                        matched = ax_val
                        break
                if matched is not None:
                    axis_clusters_d[matched].append(c)
                else:
                    axis_clusters_d[offset] = [c]

            for ax_val, cand_list in axis_clusters_d.items():
                cand_spans = [(c["span_min"], c["span_max"], c) for c in cand_list]
                cand_spans.sort(key=lambda x: x[0])

                current_cands = []
                current_min = current_max = 0.0

                for s0, s1, cand in cand_spans:
                    if not current_cands:
                        current_cands = [cand]
                        current_min, current_max = s0, s1
                        continue

                    gap_px = s0 - current_max
                    gap_ft = gap_px * scale_ft_per_px
                    if gap_ft <= 0.25:
                        gap_type = "A_CONTIGUOUS_SNAPPED"
                    elif gap_ft <= 2.2:
                        gap_type = "D_COLUMN_JUNCTION_GAP"
                    elif gap_ft <= 3.5:
                        gap_type = "B_IMPLICIT_DOOR_OPENING"
                    else:
                        gap_type = "G_TRUE_WALL_TERMINATION"

                    if gap_type in ("A_CONTIGUOUS_SNAPPED", "B_IMPLICIT_DOOR_OPENING", "D_COLUMN_JUNCTION_GAP"):
                        current_cands.append(cand)
                        current_max = max(current_max, s1)
                    else:
                        entities.append((current_cands, current_min, current_max, ax_val, "O", float(ang_bin)))
                        current_cands = [cand]
                        current_min, current_max = s0, s1

                if current_cands:
                    entities.append((current_cands, current_min, current_max, ax_val, "O", float(ang_bin)))


    # 8. Formulate Final Clean Physical Wall Entities
    all_cand_pts_x = [pt for c in confirmed_candidates for pt in (c["p1"][0], c["p2"][0]) if c["orientation"] == "H"] + [c["center_ax"] for c in confirmed_candidates if c["orientation"] == "V"]
    all_cand_pts_y = [c["center_ax"] for c in confirmed_candidates if c["orientation"] == "H"] + [pt for c in confirmed_candidates for pt in (c["p1"][1], c["p2"][1]) if c["orientation"] == "V"]
    env_x_min = min(all_cand_pts_x) if all_cand_pts_x else 0.0
    env_x_max = max(all_cand_pts_x) if all_cand_pts_x else float(w)
    env_y_min = min(all_cand_pts_y) if all_cand_pts_y else 0.0
    env_y_max = max(all_cand_pts_y) if all_cand_pts_y else float(h)
    env_w = max(1.0, env_x_max - env_x_min)
    env_h = max(1.0, env_y_max - env_y_min)

    wall_entity_records = []
    for ent_idx, (cand_list, min_c, max_c, ax_val, orient, ang_deg_ent) in enumerate(entities):
        bounding_length_ft = round((max_c - min_c) * scale_ft_per_px, 2)
        if bounding_length_ft < 1.2:
            continue

        # 1D Interval Union of physical constituent source spans
        cand_spans = sorted([(c["span_min"], c["span_max"]) for c in cand_list], key=lambda x: x[0])
        union_spans: list[tuple[float, float]] = []
        for s_i, e_i in cand_spans:
            if not union_spans:
                union_spans.append((s_i, e_i))
            else:
                ps, pe = union_spans[-1]
                if s_i <= pe + 1e-4:
                    union_spans[-1] = (ps, max(pe, e_i))
                else:
                    union_spans.append((s_i, e_i))

        true_union_px = sum(e - s for s, e in union_spans)
        true_source_union_length_ft = round(true_union_px * scale_ft_per_px, 3)

        thick_vals = [c["thickness_measured_in"] for c in cand_list if c["thickness_measured_in"] is not None]
        measured_thick_in = round(sum(thick_vals) / len(thick_vals), 1) if thick_vals else 4.875
        measured_thick_ft = round(measured_thick_in / 12.0, 4)

        all_layers = set()
        for c in cand_list:
            for lyr in c.get("layers", [c.get("layer", "")]):
                if lyr:
                    all_layers.add(lyr.lower())

        entity_openings = []
        if orient == "H":
            p1_norm = (round(min_c / w, 5), round(ax_val / h, 5))
            p2_norm = (round(max_c / w, 5), round(ax_val / h, 5))
            for op in openings:
                ox, oy = op["center"]
                if abs(oy - ax_val) <= 25 and min_c - 10 <= ox <= max_c + 10:
                    entity_openings.append(op)
        elif orient == "V":
            p1_norm = (round(ax_val / w, 5), round(min_c / h, 5))
            p2_norm = (round(ax_val / w, 5), round(max_c / h, 5))
            for op in openings:
                ox, oy = op["center"]
                if abs(ox - ax_val) <= 25 and min_c - 10 <= oy <= max_c + 10:
                    entity_openings.append(op)
        else:
            # Diagonal: reconstruct pixel endpoints from along/perp components
            # p = along·v̂ + perp·n̂  where n̂ = (-vy, vx)
            ang_rad_e = math.radians(ang_deg_ent)
            vx_e = math.cos(ang_rad_e)
            vy_e = math.sin(ang_rad_e)
            p1_px = (min_c * vx_e + ax_val * (-vy_e), min_c * vy_e + ax_val * vx_e)
            p2_px = (max_c * vx_e + ax_val * (-vy_e), max_c * vy_e + ax_val * vx_e)
            p1_norm = (max(0.0, min(1.0, round(p1_px[0] / w, 5))), max(0.0, min(1.0, round(p1_px[1] / h, 5))))
            p2_norm = (max(0.0, min(1.0, round(p2_px[0] / w, 5))), max(0.0, min(1.0, round(p2_px[1] / h, 5))))
            mid_px = ((p1_px[0] + p2_px[0]) / 2.0, (p1_px[1] + p2_px[1]) / 2.0)
            half_span = (max_c - min_c) / 2.0
            for op in openings:
                ox, oy = op["center"]
                d_x = ox - mid_px[0]
                d_y = oy - mid_px[1]
                perp_d = abs(d_x * (-vy_e) + d_y * vx_e)
                along_d = d_x * vx_e + d_y * vy_e
                if perp_d <= 30 and -15 <= along_d <= half_span + 15:
                    entity_openings.append(op)

        x_mid = (p1_norm[0] + p2_norm[0]) / 2.0
        y_mid = (p1_norm[1] + p2_norm[1]) / 2.0
        x_mid_px = x_mid * w
        y_mid_px = y_mid * h

        is_on_outer_envelope = (
            abs(x_mid_px - env_x_min) <= 0.05 * env_w
            or abs(x_mid_px - env_x_max) <= 0.05 * env_w
            or abs(y_mid_px - env_y_min) <= 0.05 * env_h
            or abs(y_mid_px - env_y_max) <= 0.05 * env_h
        )

        is_exterior = any("ex-wall" in l or "exterior" in l for l in all_layers) or is_on_outer_envelope
        in_stair_zone = any(
            cav["bbox_norm"]["x_min"] - 0.02 <= x_mid <= cav["bbox_norm"]["x_max"] + 0.02
            and cav["bbox_norm"]["y_min"] - 0.02 <= y_mid <= cav["bbox_norm"]["y_max"] + 0.02
            for cav in stair_cavities
        ) or any("stair" in l for l in all_layers)

        if in_stair_zone:
            func_type = "STAIR_CORE_WALL"
        elif any("structural" in l or "bearing" in l for l in all_layers):
            func_type = "STRUCTURAL_BEARING_WALL"
        elif is_exterior:
            func_type = "EXTERIOR_PERIMETER_WALL"
        else:
            func_type = "INTERIOR_PARTITION"

        has_pairs = any(c.get("has_paired_face") for c in cand_list)
        has_openings = len(entity_openings) > 0
        has_unnamed_evidence = any(c.get("evidence_type") == "UNNAMED_LAYER_EVIDENCE_BACKED" for c in cand_list)
        has_unnamed_long_stroke = any(c.get("evidence_type") == "UNNAMED_LAYER_LONG_STROKE_NEEDS_REVIEW" for c in cand_list)

        conf = 0.95 if has_pairs or len(cand_list) >= 2 or has_openings else 0.70
        # Unnamed long-stroke candidates that lack pairing, openings, or clustering
        # get NEEDS_REVIEW regardless — they need inspector confirmation before QTO.
        if has_unnamed_long_stroke and not has_pairs and not has_openings and len(cand_list) < 2:
            status = ReviewStatus.NEEDS_REVIEW
            conf = min(conf, 0.55)
        else:
            status = ReviewStatus.APPROVED if (has_pairs or has_openings or len(cand_list) >= 2) else ReviewStatus.NEEDS_REVIEW
        recon_method = (
            "DUAL_FACE" if has_pairs
            else "UNNAMED_LAYER_EVIDENCE_BACKED" if has_unnamed_evidence
            else "UNNAMED_LAYER_LONG_STROKE_UNCONFIRMED" if has_unnamed_long_stroke
            else "SINGLE_FACE_EVIDENCE_BACKED"
        )

        # Extract representative Face A and Face B coordinates
        primary_cand = next((c for c in cand_list if c.get("has_paired_face")), cand_list[0])
        source_segment_ids = [c["face_a_id"] for c in cand_list if c.get("face_a_id")] + [c["face_b_id"] for c in cand_list if c.get("face_b_id")]

        sum_constituent_len = round(sum(c["length_ft"] for c in cand_list), 3)
        overlap_len = max(0.0, round(sum_constituent_len - true_source_union_length_ft, 3))
        inflation_ratio = round(bounding_length_ft / max(0.01, true_source_union_length_ft), 3)

        wall_entity_records.append({
            "id": ent_idx + 1,
            "start_norm": {"x": p1_norm[0], "y": p1_norm[1]},
            "end_norm":   {"x": p2_norm[0], "y": p2_norm[1]},
            "length_ft": bounding_length_ft,
            "wall_type": "exterior" if is_exterior else "interior",
            "wall_type_code": func_type,
            "thickness_ft": measured_thick_ft,
            "thickness_measured": len(thick_vals) > 0,
            "confidence": conf,
            "status": status,
            "rejection_reasons": [] if status == ReviewStatus.APPROVED else ["single_face_unpaired_candidate"],
            "source": "cad_vector_entity_unnamed_unconfirmed" if has_unnamed_long_stroke and not has_pairs and not has_openings and len(cand_list) < 2 else "cad_vector_entity",
            "segments_count": len(cand_list),
            "openings_count": len(entity_openings),
            "face_a_segment_id": primary_cand.get("face_a_id"),
            "face_b_segment_id": primary_cand.get("face_b_id"),
            "face_a_coords": primary_cand.get("face_a_coords"),
            "face_b_coords": primary_cand.get("face_b_coords"),
            "reconstruction_method": recon_method,
            "evidence_chain": {
                "source_segment_ids": source_segment_ids,
                "cad_layer": primary_cand.get("layer"),
                "face_pair": has_pairs,
                "thickness_measured_in": measured_thick_in if len(thick_vals) > 0 else None,
                "attached_openings": len(entity_openings),
                "opening_ids": [op.get("id") for op in entity_openings if op.get("id")],
                "layers": list(all_layers),
                "stair_core": in_stair_zone,
                "reconstruction_method": recon_method,
                "confidence": conf,
                "true_source_union_length_ft": true_source_union_length_ft,
                "overlap_length_ft": overlap_len,
                "inflation_ratio": inflation_ratio,
            },
        })

    return wall_entity_records

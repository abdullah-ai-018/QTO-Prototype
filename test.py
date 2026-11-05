# import json
# import os
# import re
# import fitz  # PyMuPDF
# from dotenv import load_dotenv
# from typesafe_sdk import Noul, NoulCriteria, TypeSafeClient

# load_dotenv()
# api_key = os.getenv("Jev_Key")

# if not api_key:
#     raise ValueError("Jev_Key not found in .env file.")

# # Title-block noise to ignore if a detail sits near the border of a sheet
# NOISE_PATTERNS = [
#     r"TPG ARCHITECTURE.*",
#     r"11 PENN PLAZA.*",
#     r"112 WEST 31ST.*",
#     r"Severud Associates.*",
#     r"CONSULTING ENGINEERS.*",
#     r"NOT FOR CONSTRUCTION.*",
#     r"HARMLESS AND.*",
#     r"MACHINE READABLE.*",
# ]


# def clean_text(text: str) -> str:
#     for pattern in NOISE_PATTERNS:
#         text = re.sub(pattern, "", text, flags=re.IGNORECASE)
#     return re.sub(r"\s+", " ", text).strip()


# def load_pdf_pages(main_pdf_path: str, glossary_pdf_path: str) -> dict:
#     """Loads the schedule sheets (p22, p23), legend sheet (p1), and glossary (p1)."""
#     data = {
#         "schedule_pages": {},
#         "legend_page_text": "",
#         "glossary_lines": [],
#     }

#     with fitz.open(main_pdf_path) as doc:
#         # Page 22 (A-900) and Page 23 (A-901) hold the wall assembly diagrams
#         for page_num, sheet_name in [(22, "A-900"), (23, "A-901")]:
#             page = doc[page_num - 1]
#             blocks = page.get_text("blocks")
#             data["schedule_pages"][sheet_name] = {
#                 "width": page.rect.width,
#                 "height": page.rect.height,
#                 "blocks": blocks,
#             }

#         # Page 1 (A-100) holds the Construction Plan Legend & Key Notes (e.g., PW)
#         data["legend_page_text"] = clean_text(doc[0].get_text("text"))

#     with fitz.open(glossary_pdf_path) as doc:
#         if len(doc) > 0:
#             raw_glossary = doc[0].get_text("text")
#             data["glossary_lines"] = [
#                 clean_text(line)
#                 for line in raw_glossary.splitlines()
#                 if len(line.strip()) > 3
#             ]

#     return data


# def extract_glossary_matches(materials_text: str, glossary_lines: list[str]) -> list[str]:
#     """Finds abbreviations from the glossary PDF that appear in this wall's materials."""
#     words = set(re.findall(r"\b[A-Z]{2,5}\b", materials_text.upper()))
#     matches = []
#     for line in glossary_lines:
#         for w in words:
#             if line.upper().startswith(f"{w} ") or line.upper().startswith(f"{w}."):
#                 matches.append(line)
#                 break
#     return matches[:10]


# def extract_single_wall_data(pdf_data: dict, wall_tag: str) -> dict | None:
#     """
#     Locates a single wall tag on A-900, A-901, or A-100 Legend and extracts
#     ONLY the material callouts belonging to that specific wall.
#     """
#     tag = wall_tag.strip().rstrip("\\/").upper()
#     tag_pattern = re.compile(rf"\b{re.escape(tag)}\b", re.IGNORECASE)

#     # 1. Search Partition Schedule Sheets A-900 (p22) and A-901 (p23) using 2D coordinates
#     for sheet_name, sheet in pdf_data["schedule_pages"].items():
#         blocks = sheet["blocks"]
#         pw, ph = sheet["width"], sheet["height"]

#         # Find all text blocks on this sheet where the wall tag appears
#         anchor_blocks = [
#             b for b in blocks if b[6] == 0 and tag_pattern.search(b[4])
#         ]

#         if not anchor_blocks:
#             continue

#         collected_lines = []
#         for anchor in anchor_blocks:
#             ax = (anchor[0] + anchor[2]) / 2.0
#             ay = (anchor[1] + anchor[3]) / 2.0

#             # Collect material callout blocks inside this wall detail's box on the sheet
#             # (In CAD schedules, callouts sit directly above and around the detail tag)
#             nearby_blocks = []
#             for b in blocks:
#                 if b[6] != 0:
#                     continue
#                 bx = (b[0] + b[2]) / 2.0
#                 by = (b[1] + b[3]) / 2.0

#                 horiz_dist = abs(bx - ax)
#                 vert_offset = ay - by  # positive means block is above the tag

#                 if horiz_dist <= pw * 0.14 and (-ph * 0.08 <= vert_offset <= ph * 0.22):
#                     cleaned = clean_text(b[4])
#                     if cleaned:
#                         nearby_blocks.append((by, bx, cleaned))

#             # Sort top-to-bottom, left-to-right so the material layers read in order
#             nearby_blocks.sort(key=lambda item: (round(item[0], 1), round(item[1], 1)))
#             for _, _, text in nearby_blocks:
#                 if text not in collected_lines:
#                     collected_lines.append(text)

#         materials_text = " | ".join(collected_lines)
#         return {
#             "wall_tag": tag,
#             "source_sheet": f"Sheet {sheet_name}",
#             "wall_materials": materials_text,
#             "glossary_definitions": extract_glossary_matches(
#                 materials_text, pdf_data["glossary_lines"]
#             ),
#         }

#     # 2. Fallback: Search Sheet A-100 Construction Plan Legend (e.g., for 'PW')
#     legend_text = pdf_data["legend_page_text"]
#     legend_snippets = []
#     for match in tag_pattern.finditer(legend_text):
#         start = max(0, match.start() - 120)
#         end = min(len(legend_text), match.end() + 220)
#         legend_snippets.append(legend_text[start:end])

#     if legend_snippets:
#         materials_text = " | ".join(legend_snippets[:3])
#         return {
#             "wall_tag": tag,
#             "source_sheet": "Sheet A-100 (Construction Plan Legend)",
#             "wall_materials": materials_text,
#             "glossary_definitions": extract_glossary_matches(
#                 materials_text, pdf_data["glossary_lines"]
#             ),
#         }

#     return None


# def ask_jev_if_drywall(client: TypeSafeClient, single_wall_state: dict) -> dict:
#     """Sends ONLY the extracted single-wall material record to Jev."""
#     tag = single_wall_state["wall_tag"]

#     questions = {
#         "is_drywall": Noul(
#             instructions=(
#                 f"Read `wall_materials` for wall tag `{tag}`. "
#                 f"Based on the materials it is made of, is `{tag}` a drywall partition "
#                 f"(made with Gypsum Wall Board, GWB, or Gypsum Board)?"
#             ),
#             criteria=NoulCriteria(
#                 true=(
#                     "The wall materials specify Gypsum Wall Board (GWB), Gypsum Board, "
#                     "Type-C or Type-SCX gypsum board on studs, shaft wall, or furring."
#                 ),
#                 false=(
#                     "The wall materials describe a Glass partition system, a furniture "
#                     "vendor Privacy Wall, or bare concrete/masonry without gypsum board."
#                 ),
#             ),
#         )
#     }

#     response = client.system_one(
#         state=single_wall_state,
#         questions=questions,
#     )

#     return {
#         "model": response.model,
#         "probability": response.answers["is_drywall"].noul,
#     }


# if __name__ == "__main__":
#     main_pdf = "drywall_relevant_full_pages (1).pdf"
#     glossary_pdf = "general_glossary_information_pages (1).pdf"

#     print("Loading schedule & legend sheets from PDFs...")
#     pdf_data = load_pdf_pages(main_pdf, glossary_pdf)
#     print("Ready!\n")

#     with TypeSafeClient(api_key=api_key, model="jev-latest") as jev_client:
#         while True:
#             user_tag = input(
#                 "Enter wall tag (e.g., 1A, 5E, 7A, 8A, GL1, PW) or 'q' to quit: "
#             ).strip()
#             if user_tag.lower() == "q":
#                 break
#             if not user_tag:
#                 continue

#             # Extract ONLY the requested wall's data from the PDF
#             wall_record = extract_single_wall_data(pdf_data, user_tag)

#             if wall_record is None:
#                 print(f"\n[!] Wall tag '{user_tag}' was not found on A-900, A-901, or A-100.\n")
#                 continue

#             print("\n--- Extracted Wall Data Sent to Jev ---")
#             print(json.dumps(wall_record, indent=2))

#             # Ask Jev using only this single wall's extracted data
#             jev_result = ask_jev_if_drywall(jev_client, wall_record)
#             prob = jev_result["probability"]
#             is_drywall = "YES (Drywall)" if prob >= 0.50 else "NO (Not Drywall)"

#             print(f"\n--- Jev Verdict ({jev_result['model']}) ---")
#             print(f"Wall Tag:            {wall_record['wall_tag']}")
#             print(f"Is Drywall:          {is_drywall}")
#             print(f"Drywall Probability: {prob:.4f} ({prob * 100:.1f}%)")
#             print("---------------------------------------\n")
import json
import math
import os
import re
import sys
from collections import defaultdict
from typing import Optional
from dotenv import load_dotenv
import pymupdf as fitz
from typesafe_sdk import Noul, NoulCriteria, TypeSafeClient

# Configure stdout for UTF-8 on Windows environments if possible
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Check both .env and env
load_dotenv()
if not os.getenv("Jev_Key") and os.path.exists("env"):
    load_dotenv("env")

api_key = os.getenv("Jev_Key")

# Fallback blueprint fixture selection if primary file is missing
DEFAULT_FIXTURE_PDF = os.path.join("tests", "fixtures", "fixture_wall20.pdf")
FALLBACK_FIXTURE_PDF = os.path.join("tests", "fixtures", "fixture_door.pdf")

MAIN_PDF = os.getenv("BLUEPRINT_PDF", "drywall_relevant_full_pages (1).pdf")
if not os.path.exists(MAIN_PDF):
    if os.path.exists(DEFAULT_FIXTURE_PDF):
        MAIN_PDF = DEFAULT_FIXTURE_PDF
    elif os.path.exists(FALLBACK_FIXTURE_PDF):
        MAIN_PDF = FALLBACK_FIXTURE_PDF

GLOSSARY_PDF = "general_glossary_information_pages (1).pdf"
CACHE_FILE = "drywall_registry.json"
ANNOTATED_OUTPUT_PDF = "drywall_walls_marked_red.pdf"

PROBABILITY_THRESHOLD = 0.85

# Red color palette (RGB 0.0 - 1.0)
RED_DARK = (0.85, 0.0, 0.0)
RED_BRIGHT = (1.0, 0.0, 0.0)
RED_LIGHT_FILL = (1.0, 0.82, 0.82)

NOISE_PATTERNS = [
    r"TPG ARCHITECTURE.*",
    r"11 PENN PLAZA.*",
    r"112 WEST 31ST.*",
    r"Severud Associates.*",
    r"CONSULTING ENGINEERS.*",
    r"NOT FOR CONSTRUCTION.*",
    r"HARMLESS AND.*",
    r"MACHINE READABLE.*",
]


def clean_text(text: str) -> str:
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


# =====================================================================
# STEP 1: Discover Wall Tags & Query Jev (Cached)
# =====================================================================

def discover_tags_from_schedules(doc: fitz.Document) -> list[str]:
    """Scans Partition Types Sheets (Pages 22 & 23) and Page 1 Legend for wall tags."""
    discovered = set()
    tag_regex = re.compile(r"\b([0-9][A-Z]|[1-9][A-Z][0-9]|GL[1-9]|PW)\b", re.IGNORECASE)

    for p_num in [22, 23]:
        if p_num <= len(doc):
            text = doc[p_num - 1].get_text("text")
            for m in tag_regex.finditer(text):
                discovered.add(m.group(1).upper())

    if len(doc) >= 1:
        text = doc[0].get_text("text")
        for m in tag_regex.finditer(text):
            tag = m.group(1).upper()
            if tag in ["PW", "GL1", "GL2"]:
                discovered.add(tag)

    false_positives = {"GA", "DC", "HR", "SF", "LF", "OC", "MAX", "MIN"}
    return sorted([t for t in discovered if t not in false_positives])


def extract_wall_materials(doc: fitz.Document, wall_tag: str) -> str:
    """Extracts spatial text blocks describing the materials for a specific wall tag."""
    tag_pattern = re.compile(rf"\b{re.escape(wall_tag)}\b", re.IGNORECASE)

    for p_num in [22, 23]:
        if p_num > len(doc):
            continue
        page = doc[p_num - 1]
        blocks = page.get_text("blocks")
        pw, ph = page.rect.width, page.rect.height

        anchor_blocks = [b for b in blocks if b[6] == 0 and tag_pattern.search(b[4])]
        if not anchor_blocks:
            continue

        collected = []
        for anchor in anchor_blocks:
            ax = (anchor[0] + anchor[2]) / 2.0
            ay = (anchor[1] + anchor[3]) / 2.0
            nearby = []
            for b in blocks:
                if b[6] != 0:
                    continue
                bx = (b[0] + b[2]) / 2.0
                by = (b[1] + b[3]) / 2.0
                if abs(bx - ax) <= pw * 0.14 and (-ph * 0.08 <= (ay - by) <= ph * 0.22):
                    txt = clean_text(b[4])
                    if txt:
                        nearby.append((by, bx, txt))
            nearby.sort(key=lambda x: (round(x[0], 1), round(x[1], 1)))
            for _, _, txt in nearby:
                if txt not in collected:
                    collected.append(txt)

        if collected:
            return " | ".join(collected)

    legend_text = clean_text(doc[0].get_text("text"))
    snippets = []
    for match in tag_pattern.finditer(legend_text):
        start = max(0, match.start() - 100)
        end = min(len(legend_text), match.end() + 200)
        snippets.append(legend_text[start:end])

    return " | ".join(snippets[:2]) if snippets else "No specific assembly details located."


def evaluate_with_jev(client: TypeSafeClient, wall_tag: str, materials: str) -> float:
    """Queries Jev for the probability that the wall tag is drywall."""
    state = {
        "wall_tag": wall_tag,
        "materials": materials,
        "context": "GWB = Gypsum Wall Board (Drywall). GYP. BD. = Gypsum Board (Drywall). GL = Glass. PW = Privacy Wall.",
    }

    questions = {
        "is_drywall": Noul(
            instructions=(
                f"Read the materials for wall tag `{wall_tag}`. Is this a drywall partition "
                f"(constructed using Gypsum Wall Board / GWB / Gypsum Board)?"
            ),
            criteria=NoulCriteria(
                true="Specifies Gypsum Wall Board (GWB), Gypsum Board, or drywall on metal studs, C-H studs, or furring.",
                false="Specifies glass officefront system (GL1/GL2), demountable furniture privacy wall (PW), or masonry without gypsum.",
            ),
        )
    }

    response = client.system_one(state=state, questions=questions)
    return round(response.answers["is_drywall"].noul, 4)


def get_wall_registry(doc: fitz.Document, client: Optional[TypeSafeClient] = None, force_refresh: bool = False) -> dict:
    """Loads cached Jev evaluations or queries Jev and saves results to JSON."""
    if os.path.exists(CACHE_FILE) and not force_refresh:
        print(f"[CACHE] Loaded cached Jev evaluations from '{CACHE_FILE}'.")
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    if client is None:
        raise ValueError("TypeSafeClient / Jev_Key is required to query Jev when cache is not available.")

    print("[JEV] Extracting wall descriptions and querying Jev...")
    tags = discover_tags_from_schedules(doc)
    print(f"[DISCOVERY] Found {len(tags)} candidate tags: {tags}\n")

    registry = {}
    for tag in tags:
        materials = extract_wall_materials(doc, tag)
        prob = evaluate_with_jev(client, tag, materials)
        registry[tag] = {
            "wall_tag": tag,
            "probability": prob,
            "materials_excerpt": materials[:160] + ("..." if len(materials) > 160 else ""),
        }
        status = "DRYWALL (>= 0.90)" if prob >= PROBABILITY_THRESHOLD else "SKIPPED (< 0.90)"
        print(f"  Tag: {tag:<4} | Prob: {prob * 100:5.1f}% | {status}")

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)

    print(f"\n[CACHE] Saved classification registry to '{CACHE_FILE}'.\n")
    return registry


# =====================================================================
# STEP 2: Vector Geometry Helpers for Tracing Walls on Floor Plans
# =====================================================================

def point_to_segment_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> tuple[float, float, float]:
    """Returns (distance, closest_x, closest_y) from point (px, py) to segment (x1, y1)-(x2, y2)."""
    dx, dy = x2 - x1, y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq < 1e-9:
        return math.hypot(px - x1, py - y1), x1, y1
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / len_sq))
    cx, cy = x1 + t * dx, y1 + t * dy
    return math.hypot(px - cx, py - cy), cx, cy


def angle_diff(a1: float, a2: float) -> float:
    """Smallest angle difference in radians between two undirected line angles in [0, pi)."""
    diff = abs(a1 - a2) % math.pi
    return min(diff, math.pi - diff)


def extract_page_segments(page: fitz.Page) -> list[dict]:
    """
    Extracts straight vector line segments from the PDF page's CAD drawings.
    Returns a list of segment dicts with coordinates, length, and angle.
    """
    raw_drawings = page.get_drawings()
    max_wall_len = page.rect.width * 0.45  # Ignore full-sheet grid lines and borders
    drawing_cutoff_x = page.rect.width * 0.78  # Ignore right-side notes/titleblock column

    segments = []
    raw_lines = []

    for path in raw_drawings:
        rect = path.get("rect")
        if rect and rect.x0 > drawing_cutoff_x:
            continue

        for item in path.get("items", []):
            kind = item[0]
            if kind == "l":
                p1, p2 = item[1], item[2]
                raw_lines.append((p1.x, p1.y, p2.x, p2.y))
            elif kind == "re":
                r = item[1]
                raw_lines.extend([
                    (r.x0, r.y0, r.x1, r.y0),
                    (r.x1, r.y0, r.x1, r.y1),
                    (r.x1, r.y1, r.x0, r.y1),
                    (r.x0, r.y1, r.x0, r.y0),
                ])
            elif kind == "qu":
                q = item[1]
                raw_lines.extend([
                    (q.ul.x, q.ul.y, q.ur.x, q.ur.y),
                    (q.ur.x, q.ur.y, q.lr.x, q.lr.y),
                    (q.lr.x, q.lr.y, q.ll.x, q.ll.y),
                    (q.ll.x, q.ll.y, q.ul.x, q.ul.y),
                ])

    for x1, y1, x2, y2 in raw_lines:
        if min(x1, x2) > drawing_cutoff_x:
            continue
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 4.0 or length > max_wall_len:
            continue

        theta = math.atan2(y2 - y1, x2 - x1) % math.pi
        segments.append({
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "length": length,
            "angle": theta,
            "min_x": min(x1, x2),
            "max_x": max(x1, x2),
            "min_y": min(y1, y2),
            "max_y": max(y1, y2),
        })

    return segments


def find_leader_endpoint(
    tc_x: float, tc_y: float, tag_radius: float, segments: list[dict]
) -> tuple[float, float, dict | None]:
    """
    Checks if a CAD leader line starts near the edge of the tag callout box
    and points outward to a wall. Returns (anchor_x, anchor_y, leader_segment).
    """
    best_leader = None
    best_score = float("inf")
    anchor_x, anchor_y = tc_x, tc_y

    min_start = max(3.0, tag_radius * 0.45)
    max_start = tag_radius + 16.0

    for seg in segments:
        if not (6.0 <= seg["length"] <= 110.0):
            continue
        # Quick bounding box check around tag center
        if (
            seg["max_x"] < tc_x - 130
            or seg["min_x"] > tc_x + 130
            or seg["max_y"] < tc_y - 130
            or seg["min_y"] > tc_y + 130
        ):
            continue

        d1 = math.hypot(seg["x1"] - tc_x, seg["y1"] - tc_y)
        d2 = math.hypot(seg["x2"] - tc_x, seg["y2"] - tc_y)

        # Case 1: Endpoint 1 is on the tag diamond, Endpoint 2 points out to the wall
        if min_start <= d1 <= max_start and d2 > d1 + 6.0:
            if d1 < best_score:
                best_score = d1
                best_leader = seg
                anchor_x, anchor_y = seg["x2"], seg["y2"]

        # Case 2: Endpoint 2 is on the tag diamond, Endpoint 1 points out to the wall
        elif min_start <= d2 <= max_start and d1 > d2 + 6.0:
            if d2 < best_score:
                best_score = d2
                best_leader = seg
                anchor_x, anchor_y = seg["x1"], seg["y1"]

    return anchor_x, anchor_y, best_leader


def trace_wall_from_anchor(
    anchor_x: float,
    anchor_y: float,
    tc_x: float,
    tc_y: float,
    tag_radius: float,
    segments: list[dict],
    leader_seg: dict | None,
) -> dict | None:
    """
    1. Finds the closest wall line segment to (anchor_x, anchor_y).
    2. Chains colinear wall segments along the same axis (bridging door/joint gaps).
    3. Captures the parallel opposite face of the double-line partition wall.
    """
    search_radius = 24.0 if leader_seg is not None else 42.0
    seed_seg = None
    best_dist = search_radius

    for seg in segments:
        # A wall segment should be longer than the small edges of a tag callout box
        if seg["length"] < 12.0 or seg is leader_seg:
            continue

        # Ignore segments whose midpoint is right inside the tag text box itself
        mid_x = (seg["x1"] + seg["x2"]) / 2.0
        mid_y = (seg["y1"] + seg["y2"]) / 2.0
        if math.hypot(mid_x - tc_x, mid_y - tc_y) < tag_radius * 0.9 and seg["length"] < 22.0:
            continue

        if (
            seg["max_x"] < anchor_x - search_radius
            or seg["min_x"] > anchor_x + search_radius
            or seg["max_y"] < anchor_y - search_radius
            or seg["min_y"] > anchor_y + search_radius
        ):
            continue

        dist, _, _ = point_to_segment_distance(
            anchor_x, anchor_y, seg["x1"], seg["y1"], seg["x2"], seg["y2"]
        )
        if dist < best_dist:
            best_dist = dist
            seed_seg = seg

    if seed_seg is None:
        return None

    # Set up local 2D axis (ux, uy) along the seed wall segment
    ox, oy = seed_seg["x1"], seed_seg["y1"]
    ux = (seed_seg["x2"] - ox) / seed_seg["length"]
    uy = (seed_seg["y2"] - oy) / seed_seg["length"]
    seed_angle = seed_seg["angle"]

    # Project all parallel segments onto (t_along_wall, d_perpendicular)
    colinear_candidates = []
    parallel_candidates = []
    max_angle_tol = math.radians(3.5)

    for seg in segments:
        if seg["length"] < 8.0 or seg is leader_seg:
            continue
        if angle_diff(seg["angle"], seed_angle) > max_angle_tol:
            continue

        t1 = (seg["x1"] - ox) * ux + (seg["y1"] - oy) * uy
        t2 = (seg["x2"] - ox) * ux + (seg["y2"] - oy) * uy
        d1 = -(seg["x1"] - ox) * uy + (seg["y1"] - oy) * ux
        d2 = -(seg["x2"] - ox) * uy + (seg["y2"] - oy) * ux

        t_min, t_max = min(t1, t2), max(t1, t2)
        d_avg = 0.5 * (d1 + d2)

        if abs(d_avg) <= 2.5:
            colinear_candidates.append((t_min, t_max, d_avg, seg))
        elif 1.0 <= abs(d_avg) <= 13.0:
            parallel_candidates.append((t_min, t_max, d_avg, seg))

    # Chain colinear segments outward from the seed segment [0, seed_seg["length"]]
    t_start = 0.0
    t_end = seed_seg["length"]
    max_gap = 28.0  # Bridges door openings and wall intersections

    colinear_candidates.sort(key=lambda item: item[0])
    changed = True
    traced_segments = [seed_seg]

    while changed:
        changed = False
        for t_min, t_max, _, seg in colinear_candidates:
            if seg in traced_segments:
                continue
            # Check if segment overlaps or is within max_gap of [t_start, t_end]
            if t_max >= t_start - max_gap and t_min <= t_end + max_gap:
                t_start = min(t_start, t_min)
                t_end = max(t_end, t_max)
                traced_segments.append(seg)
                changed = True

    # Collect parallel double-line segments (opposite face of the drywall assembly)
    twin_offsets = [0.0]
    for t_min, t_max, d_avg, seg in parallel_candidates:
        # Must overlap the traced wall span
        overlap = min(t_end, t_max) - max(t_start, t_min)
        if overlap >= 4.0:
            traced_segments.append(seg)
            twin_offsets.append(d_avg)

    # Compute the centerline spine of the traced wall run
    d_center = sum(twin_offsets) / len(twin_offsets)
    spine_x1 = ox + t_start * ux - d_center * uy
    spine_y1 = oy + t_start * uy + d_center * ux
    spine_x2 = ox + t_end * ux - d_center * uy
    spine_y2 = oy + t_end * uy + d_center * ux

    return {
        "spine": (spine_x1, spine_y1, spine_x2, spine_y2),
        "segments": traced_segments,
        "leader": leader_seg,
    }


# =====================================================================
# STEP 3: Annotate Both the Walls and Tags in Red on the Floor Plans
# =====================================================================

def annotate_walls_and_tags_in_red(doc: fitz.Document, qualified_tags: dict):
    """
    Finds all instances of qualified tags (prob >= 0.90) on the floor plans,
    traces their physical wall segments, and marks both the walls and tags in RED.
    """
    total_tags_marked = 0
    total_wall_segments_marked = 0
    summary_by_sheet = defaultdict(lambda: defaultdict(int))

    # Skip the Partition Schedule pages (22 & 23)
    schedule_pages = {22, 23}

    print(
        f"[ANNOTATION] Tracing & marking walls in RED for tags (P >= {PROBABILITY_THRESHOLD}): "
        f"{list(qualified_tags.keys())}"
    )

    for page_idx, page in enumerate(doc):
        page_num = page_idx + 1
        if page_num in schedule_pages:
            continue

        page_text = page.get_text("text")
        sheet_match = re.search(r"\b(A-\d{3})\b", page_text)
        sheet_label = sheet_match.group(1) if sheet_match else f"Page_{page_num}"

        # Use word-level extraction so we match exact tags and ignore the right-hand Notes column
        drawing_cutoff_x = page.rect.width * 0.78
        words = page.get_text("words")

        # Group matching word boxes on this page
        matched_tag_boxes = []
        for w in words:
            x0, y0, x1, y1, raw_word = w[0], w[1], w[2], w[3], w[4]
            if x0 > drawing_cutoff_x:
                continue
            cleaned_token = re.sub(r"[^A-Z0-9]", "", raw_word.upper())
            if cleaned_token in qualified_tags:
                matched_tag_boxes.append((cleaned_token, fitz.Rect(x0, y0, x1, y1)))

        if not matched_tag_boxes:
            continue

        # Extract CAD vector segments once for this floor plan page
        page_segments = extract_page_segments(page)
        shape = page.new_shape()

        for tag, rect in matched_tag_boxes:
            prob = qualified_tags[tag]["probability"]
            tc_x = (rect.x0 + rect.x1) / 2.0
            tc_y = (rect.y0 + rect.y1) / 2.0
            tag_radius = max(rect.width, rect.height) * 1.25

            # 1. Locate leader line (if any) and trace the connected wall geometry
            anchor_x, anchor_y, leader_seg = find_leader_endpoint(
                tc_x, tc_y, tag_radius, page_segments
            )
            traced_wall = trace_wall_from_anchor(
                anchor_x, anchor_y, tc_x, tc_y, tag_radius, page_segments, leader_seg
            )

            # 2. Mark the physical wall in RED
            if traced_wall is not None:
                sx1, sy1, sx2, sy2 = traced_wall["spine"]

                # Draw a semi-transparent wide RED highlight band along the full wall spine
                shape.draw_line(fitz.Point(sx1, sy1), fitz.Point(sx2, sy2))
                shape.finish(
                    color=RED_BRIGHT,
                    width=8.0,
                    stroke_opacity=0.32,
                    lineCap=1,
                )

                # Trace each individual wall face segment in crisp dark RED
                for seg in traced_wall["segments"]:
                    shape.draw_line(
                        fitz.Point(seg["x1"], seg["y1"]),
                        fitz.Point(seg["x2"], seg["y2"]),
                    )
                shape.finish(
                    color=RED_DARK,
                    width=2.2,
                    stroke_opacity=0.90,
                )

                # Highlight the leader line connecting the tag to the wall in red
                if leader_seg is not None:
                    shape.draw_line(
                        fitz.Point(leader_seg["x1"], leader_seg["y1"]),
                        fitz.Point(leader_seg["x2"], leader_seg["y2"]),
                    )
                    shape.finish(color=RED_DARK, width=1.5, stroke_opacity=0.85)

                # Add a clickable PDF line annotation along the wall spine
                wall_annot = page.add_line_annot(fitz.Point(sx1, sy1), fitz.Point(sx2, sy2))
                wall_annot.set_colors(stroke=RED_BRIGHT)
                wall_annot.set_border(width=2.5)
                wall_annot.set_opacity(0.75)
                wall_annot.set_info(
                    title="Jev Drywall Detector",
                    content=f"DRYWALL WALL: {tag}\nJev Probability: {prob * 100:.1f}%\nSheet: {sheet_label}",
                )
                wall_annot.update()

                total_wall_segments_marked += len(traced_wall["segments"])

            # 3. Mark the Wall Tag callout box itself in RED
            tag_box = fitz.Rect(rect.x0 - 4, rect.y0 - 3, rect.x1 + 4, rect.y1 + 3)
            shape.draw_rect(tag_box)
            shape.finish(
                color=RED_DARK,
                fill=RED_LIGHT_FILL,
                width=1.8,
                stroke_opacity=0.95,
                fill_opacity=0.45,
            )

            tag_annot = page.add_rect_annot(tag_box)
            tag_annot.set_colors(stroke=RED_DARK)
            tag_annot.set_border(width=1.5)
            tag_annot.set_info(
                title="Jev Drywall Tag",
                content=f"DRYWALL TAG: {tag}\nJev Probability: {prob * 100:.1f}%\nSheet: {sheet_label}",
            )
            tag_annot.update()

            total_tags_marked += 1
            summary_by_sheet[f"Page {page_num} ({sheet_label})"][tag] += 1

        # Commit all red vector wall drawings to the page overlay
        shape.commit(overlay=True)

    return total_tags_marked, total_wall_segments_marked, summary_by_sheet


# =====================================================================
# Main Execution
# =====================================================================

if __name__ == "__main__":
    # Support specifying blueprint path via command line argument
    target_pdf = sys.argv[1] if len(sys.argv) > 1 and os.path.exists(sys.argv[1]) else MAIN_PDF
    if not os.path.exists(target_pdf):
        print(f"[!] Target blueprint PDF not found: {target_pdf}")
        sys.exit(1)

    print(f"Opening blueprint PDF: {target_pdf}...")
    doc = fitz.open(target_pdf)

    # Load from cache if available; otherwise initialize TypeSafeClient if key exists
    if os.path.exists(CACHE_FILE):
        registry = get_wall_registry(doc, client=None, force_refresh=False)
    elif api_key:
        with TypeSafeClient(api_key=api_key, model="jev-latest") as jev_client:
            registry = get_wall_registry(doc, jev_client, force_refresh=False)
    else:
        raise ValueError(
            "Jev_Key not found in .env or env file, and no drywall_registry.json cache file exists."
        )

    # Filter for walls with Jev probability >= 0.90
    qualified_tags = {
        tag: data
        for tag, data in registry.items()
        if data.get("probability", 0.0) >= PROBABILITY_THRESHOLD
    }

    print("=======================================================")
    print(f" QUALIFIED DRYWALL TAGS (Probability >= {PROBABILITY_THRESHOLD * 100:.0f}%)")
    print("=======================================================")
    for tag, data in qualified_tags.items():
        print(f"  - Tag: {tag:<4} | Jev Probability: {data['probability'] * 100:.1f}%")
    print("=======================================================\n")

    tags_count, segments_count, summary = annotate_walls_and_tags_in_red(doc, qualified_tags)

    doc.save(ANNOTATED_OUTPUT_PDF, garbage=4, deflate=True)
    doc.close()

    print("\n=======================================================")
    print(" RED WALL & TAG ANNOTATION SUMMARY")
    print("=======================================================")
    print(f"Total drywall tags marked in red:          {tags_count}")
    print(f"Total CAD wall face segments traced in red: {segments_count}")
    print(f"Output PDF saved to:                       {ANNOTATED_OUTPUT_PDF}\n")

    for sheet, tag_counts in summary.items():
        print(f"[Sheet] {sheet}:")
        for tag, occ in tag_counts.items():
            print(f"    - Tag '{tag}': {occ} drywall assembly run(s) marked in RED")
    print("=======================================================\n")
"""
Dual red visual and interactive PDF annotation engine.
Renders semi-transparent wide red highlight bands, crisp dark red CAD edges,
callout tag boxes, and PyMuPDF vector annotations with provenance tooltips.
"""

from __future__ import annotations
import os
from typing import Any, Dict, List, Optional
import pymupdf as fitz

from qto.dedup import WallRun
from qto.tags import TagInstance

# Red color palette (RGB 0.0 - 1.0)
RED_DARK = (0.85, 0.0, 0.0)
RED_BRIGHT = (1.0, 0.0, 0.0)
RED_LIGHT_FILL = (1.0, 0.82, 0.82)
AMBER_OPENING = (0.96, 0.62, 0.04)


def annotate_blueprint_pdf(
    input_pdf_path: str,
    runs: List[WallRun],
    tag_instances: List[TagInstance],
    output_pdf_path: str,
    registry: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """
    Renders dual-red visual vector drawings and clickable interactive annotations on the input blueprint PDF.
    - Bright red band (width 8.0, 0.32 alpha) along centerline spine.
    - Dark red crisp edges (width 2.2, 0.90 alpha) on traced CAD face segments.
    - Dark red leader lines (width 1.5, 0.85 alpha).
    - Red filled tag callout boxes (stroke 1.8, 0.95 alpha; fill 0.45 alpha).
    - Interactive tooltips containing Wall Run ID, tag, gross LF, net LF, and Jev probability.
    Saves optimized document to output_pdf_path with deflate=True, garbage=4.
    """
    if not os.path.exists(input_pdf_path):
        raise FileNotFoundError(f"Input blueprint PDF not found: {input_pdf_path}")

    # Ensure parent output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_pdf_path)), exist_ok=True)

    doc = fitz.open(input_pdf_path)

    # Group runs by page_num (1-indexed)
    runs_by_page: Dict[int, List[WallRun]] = {}
    for r in runs:
        runs_by_page.setdefault(r.page_num, []).append(r)

    # Group tag instances by page_num (1-indexed)
    tags_by_page: Dict[int, List[TagInstance]] = {}
    for t in tag_instances:
        tags_by_page.setdefault(t.page_num, []).append(t)

    for page_idx, page in enumerate(doc):
        page_num = page_idx + 1
        page_runs = runs_by_page.get(page_num, [])
        page_tags = tags_by_page.get(page_num, [])

        if not page_runs and not page_tags:
            continue

        sheet_label = page_runs[0].sheet_label if page_runs else f"Page_{page_num}"
        shape = page.new_shape()

        # 1. Annotate Wall Runs
        for run in page_runs:
            s = run.spine
            prob_str = ""
            if registry and run.tag in registry:
                prob = registry[run.tag].get("probability", 1.0)
                prob_str = f"\nJev Probability: {prob * 100:.1f}%"

            # Determine highlight band width: standard 8.0pt, or expand to physical thickness if wider
            thick_pt = getattr(run, "thickness_pt", None)
            band_width = max(8.0, float(thick_pt)) if (thick_pt is not None and thick_pt > 0) else 8.0

            # Draw semi-transparent bright red highlight band along centerline spine
            shape.draw_line(fitz.Point(s.x1, s.y1), fitz.Point(s.x2, s.y2))
            shape.finish(
                color=RED_BRIGHT,
                width=band_width,
                stroke_opacity=0.32,
                lineCap=1,
            )

            # Draw traced wall face segments in crisp dark red
            for seg in run.segments:
                shape.draw_line(fitz.Point(seg.x1, seg.y1), fitz.Point(seg.x2, seg.y2))
            shape.finish(
                color=RED_DARK,
                width=2.2,
                stroke_opacity=0.90,
            )

            # Draw leader line if present
            if run.leader_segment is not None:
                ls = run.leader_segment
                shape.draw_line(fitz.Point(ls.x1, ls.y1), fitz.Point(ls.x2, ls.y2))
                shape.finish(
                    color=RED_DARK,
                    width=1.5,
                    stroke_opacity=0.85,
                )

            # Format thickness provenance
            thick_str = ""
            thick_in = getattr(run, "thickness_in", None)
            if thick_in is not None:
                source_lbl = "Measured" if getattr(run, "thickness_measured", False) else "Nominal"
                thick_str = f"\nThickness: {thick_in:.2f}\" ({source_lbl})"

            # Format height & verification provenance
            height_val = getattr(run, "height_ft", 10.0) or 10.0
            h_verified = getattr(run, "is_height_verified", False)
            h_source = getattr(run, "height_source", "") or ("Verified" if h_verified else "Default")
            callout = getattr(run, "section_callout_tag", None)
            callout_str = f" [{callout}]" if callout else ""
            height_str = f"\nHeight: {height_val:.2f}' ({h_source}{callout_str})"

            # Format structured material layers
            layers_str = ""
            layers = getattr(run, "material_layers", None)
            if layers:
                layer_parts = [f"{l.get('side', '')}: {l.get('material', '')}" for l in layers if l.get('material')]
                if layer_parts:
                    layers_str = f"\nLayers: {' | '.join(layer_parts)}"

            # Add interactive vector line annotation on wall spine
            wall_annot = page.add_line_annot(fitz.Point(s.x1, s.y1), fitz.Point(s.x2, s.y2))
            wall_annot.set_colors(stroke=RED_BRIGHT)
            wall_annot.set_border(width=2.5)
            wall_annot.set_opacity(0.75)
            wall_annot.set_info(
                title=f"Wall {run.run_id} ({run.tag})",
                content=(
                    f"DRYWALL WALL: {run.tag} [{run.run_id}]\n"
                    f"Gross LF: {run.gross_length_ft:.2f}' | Net LF: {run.net_length_ft:.2f}'\n"
                    f"Opening Deductions: {run.opening_deduction_ft:.2f}' ({len(run.openings)} openings){thick_str}{height_str}\n"
                    f"Status: {run.status}{prob_str}{layers_str}\n"
                    f"Sheet: {sheet_label}"
                ),
            )
            wall_annot.update()

        # 2. Annotate Wall Tag Callout Boxes
        for tag_inst in page_tags:
            b = tag_inst.bbox
            tag_box = fitz.Rect(b.x0 - 4, b.y0 - 3, b.x1 + 4, b.y1 + 3)

            prob_str = ""
            if registry and tag_inst.tag in registry:
                prob = registry[tag_inst.tag].get("probability", 1.0)
                prob_str = f"\nJev Probability: {prob * 100:.1f}%"

            # Draw red callout box
            shape.draw_rect(tag_box)
            shape.finish(
                color=RED_DARK,
                fill=RED_LIGHT_FILL,
                width=1.8,
                stroke_opacity=0.95,
                fill_opacity=0.45,
            )

            # Add interactive rect annotation
            tag_annot = page.add_rect_annot(tag_box)
            tag_annot.set_colors(stroke=RED_DARK)
            tag_annot.set_border(width=1.5)
            tag_annot.set_info(
                title=f"Tag {tag_inst.tag}",
                content=f"DRYWALL TAG: {tag_inst.tag}{prob_str}\nSheet: {sheet_label}",
            )
            tag_annot.update()

        # Commit all vector drawings to the page overlay
        shape.commit(overlay=True)

    # Save to disk
    doc.save(output_pdf_path, garbage=4, deflate=True)
    doc.close()

    return output_pdf_path

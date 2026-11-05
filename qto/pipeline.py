"""
Drywall QTO Orchestration Pipeline implementing stages S00 to S16:
- S00: Run Setup & Environment Profiling
- S01: PDF Page Indexing & Sheet Classification
- S02: Partition Schedule & Tag Discovery
- S03: Assembly Description Extraction
- S04: Jev / Mock Classification
- S05: Assembly Attributes Parsing
- S06: Scale Calibration & Conversion Factor
- S07: CAD Vector Extraction & Noise Filtering
- S08: Tag Instances on Floor Plans
- S09: Leader Endpoint & Seed Segment Search
- S10: Wall Tracing & Collinear Chaining
- S11: Opening Deduction Engine (2'-8' gaps & door arcs)
- S12: Twin Face Matching & Centerline Spine Generation
- S13: Wall Run Deduplication & Tag Conflict Flagging
- S14: Takeoff Quantities Calculation
- S15: Run Output Export (runs/<run_id>/output.json)
- S16: Dual Red Vector PDF Annotation (runs/<run_id>/annotated.pdf)
"""

from __future__ import annotations
import hashlib
import json
import math
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import pymupdf as fitz

from qto.geometry import Point, Segment, BoundingBox
from qto.scale import detect_scale_from_page, parse_scale_string, DEFAULT_FT_PER_PT
from qto.tags import (
    discover_tags_from_schedules,
    find_tag_instances_on_page,
    TagInstance,
)
from qto.assemblies import extract_wall_materials, parse_assembly_attributes
from qto.classify.jev import (
    get_wall_registry,
    load_environment_credentials,
    PROBABILITY_THRESHOLD,
    DEFAULT_CACHE_FILE,
)
from qto.segments import extract_page_linework, PageLinework
from qto.trace_walls import (
    find_leader_endpoint,
    find_seed_segment,
    trace_wall_from_seed,
    TracedWall,
)
from qto.dedup import create_wall_run, deduplicate_wall_runs, WallRun
from qto.annotate import annotate_blueprint_pdf
from qto.quantities import calculate_takeoff, TakeoffResult
from qto.export import export_takeoff_excel


def compute_file_sha256(filepath: str) -> str:
    """Computes SHA-256 hash of a file for audit provenance."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


class QTOPipeline:
    """Production pipeline orchestrating stages S00 through S16."""

    def __init__(
        self,
        pdf_path: str,
        run_id: Optional[str] = None,
        output_dir: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        selected_pages: Optional[List[int]] = None,
    ):
        self.pdf_path = os.path.abspath(pdf_path)
        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(f"Input PDF not found: {self.pdf_path}")

        self.config = config or {}
        sp = selected_pages or self.config.get("selected_pages")
        self.selected_pages: Optional[List[int]] = [int(p) for p in sp] if sp else None

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        short_id = uuid.uuid4().hex[:6]
        self.run_id = run_id or f"run_{timestamp_str}_{short_id}"

        base_dir = output_dir or os.path.join(os.getcwd(), "runs", self.run_id)
        self.output_dir = os.path.abspath(base_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        self.output_json_path = os.path.join(self.output_dir, "output.json")
        self.qto_excel_path = os.path.join(self.output_dir, "qto.xlsx")
        self.annotated_pdf_path = os.path.join(self.output_dir, "annotated.pdf")

        # Pipeline runtime state
        self.doc: Optional[fitz.Document] = None
        self.pdf_hash = ""
        self.sheets: List[Dict[str, Any]] = []
        self.discovered_tags: List[str] = []
        self.materials_map: Dict[str, str] = {}
        self.wall_registry: Dict[str, Dict[str, Any]] = {}
        self.qualified_tags: Dict[str, Dict[str, Any]] = {}
        self.assembly_attributes: Dict[str, Dict[str, Any]] = {}
        self.page_scales: Dict[int, float] = {}
        self.page_linework: Dict[int, PageLinework] = {}
        self.tag_instances: List[TagInstance] = []
        self.raw_wall_runs: List[WallRun] = []
        self.deduped_wall_runs: List[WallRun] = []
        self.openings_catalog: List[Dict[str, Any]] = []
        self.takeoff_result: Optional[TakeoffResult] = None
        self.height_review_items: List[Dict[str, Any]] = []
        self.takeoff_summary: Dict[str, Any] = {}
        self.stage_timings: Dict[str, float] = {}

    def run(self, selected_pages: Optional[List[int]] = None) -> Dict[str, Any]:
        """Executes all stages S00 to S16."""
        if selected_pages is not None:
            self.selected_pages = [int(p) for p in selected_pages]

        start_time = time.time()
        print(f"\n=======================================================")
        print(f" DRY-WALL QTO PIPELINE: {self.run_id}")
        print(f" PDF: {self.pdf_path}")
        print(f" Output Dir: {self.output_dir}")
        print(f"=======================================================\n")

        try:
            self._stage_s00_run_setup()
            self._stage_s01_sheet_indexing()
            self._stage_s02_tag_discovery()
            self._stage_s03_assembly_extraction()
            self._stage_s04_classification()
            self._stage_s05_assembly_attributes()
            self._stage_s06_scale_calibration()
            self._stage_s07_vector_extraction()
            self._stage_s08_tag_instances()
            self._stage_s09_to_s12_wall_tracing()
            self._stage_s13_deduplication()
            self._stage_s13b_section_height_verification()
            self._stage_s14_takeoff_quantities()
            self._stage_s15_export_output()
            self._stage_s16_annotate_pdf()

            total_elapsed = time.time() - start_time
            print(f"\n[PIPELINE COMPLETE] Finished {self.run_id} in {total_elapsed:.2f}s")
            print(f"  Annotated PDF: {self.annotated_pdf_path}")
            print(f"  Output JSON:   {self.output_json_path}\n")

            return self.takeoff_summary

        finally:
            if self.doc is not None:
                try:
                    self.doc.close()
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # STAGES IMPLEMENTATION
    # -------------------------------------------------------------------------

    def _stage_s00_run_setup(self):
        """S00: Run setup and PDF hashing."""
        t0 = time.time()
        self.pdf_hash = compute_file_sha256(self.pdf_path)
        self.doc = fitz.open(self.pdf_path)

        # Validate selected_pages bounds if provided
        if self.selected_pages is not None:
            total_doc_pages = len(self.doc)
            invalid_pages = [p for p in self.selected_pages if p < 1 or p > total_doc_pages]
            if invalid_pages:
                raise ValueError(
                    f"Invalid selected_pages {invalid_pages}: Blueprint has {total_doc_pages} pages (1-indexed)."
                )

        self.stage_timings["S00_run_setup"] = round(time.time() - t0, 4)
        print(f"[S00] Initialized run {self.run_id} | SHA-256: {self.pdf_hash[:12]}...")

    def _stage_s01_sheet_indexing(self):
        """S01: Index pages and extract sheet numbers from title blocks."""
        t0 = time.time()
        assert self.doc is not None
        from qto.sheet_index import index_blueprint_sheets

        self.sheets = index_blueprint_sheets(self.doc)
        self.stage_timings["S01_sheet_indexing"] = round(time.time() - t0, 4)
        print(f"[S01] Indexed {len(self.sheets)} pages.")

    def _stage_s02_tag_discovery(self):
        """S02: Discover partition schedule tags using lumber negative lookahead regex."""
        t0 = time.time()
        assert self.doc is not None

        # Identify schedule sheets
        schedule_pages = [
            s["page_num"] - 1 for s in self.sheets if s["page_type"] == "PARTITION_SCHEDULE"
        ]
        self.schedule_pages = schedule_pages

        self.discovered_tags = discover_tags_from_schedules(
            self.doc, schedule_page_indices=schedule_pages or None
        )
        self.stage_timings["S02_tag_discovery"] = round(time.time() - t0, 4)
        print(f"[S02] Discovered {len(self.discovered_tags)} wall tags: {self.discovered_tags}")

    def _stage_s03_assembly_extraction(self):
        """S03: Spatial text extraction of assembly descriptions around schedule tags."""
        t0 = time.time()
        assert self.doc is not None
        self.materials_map = {}

        schedule_pages = getattr(self, "schedule_pages", None)
        if not schedule_pages:
            schedule_pages = [
                s["page_num"] - 1 for s in self.sheets if s.get("page_type") == "PARTITION_SCHEDULE"
            ]

        for tag in self.discovered_tags:
            materials = extract_wall_materials(self.doc, tag, schedule_page_indices=schedule_pages or None)
            self.materials_map[tag] = materials

        self.stage_timings["S03_assembly_extraction"] = round(time.time() - t0, 4)
        print(f"[S03] Extracted material descriptions for {len(self.materials_map)} tags.")

    def _stage_s04_classification(self):
        """S04: Evaluate tags with Jev model (with fallback to mock and disk caching)."""
        t0 = time.time()
        api_key = load_environment_credentials()
        cache_path = os.path.join(os.path.dirname(self.output_dir), DEFAULT_CACHE_FILE)
        if not os.path.exists(cache_path):
            cache_path = DEFAULT_CACHE_FILE

        self.wall_registry = get_wall_registry(
            tags=self.discovered_tags,
            materials_map=self.materials_map,
            cache_file=cache_path,
            api_key=api_key,
        )

        self.qualified_tags = {
            tag: data
            for tag, data in self.wall_registry.items()
            if data["probability"] >= PROBABILITY_THRESHOLD
        }

        self.stage_timings["S04_classification"] = round(time.time() - t0, 4)
        print(
            f"[S04] Classified tags. {len(self.qualified_tags)} qualified as DRYWALL (>= {PROBABILITY_THRESHOLD * 100:.0f}%): "
            f"{list(self.qualified_tags.keys())}"
        )

    def _stage_s05_assembly_attributes(self):
        """S05: Parse physical wall attributes (studs, spacing, board, layers)."""
        t0 = time.time()
        self.assembly_attributes = {}
        for tag, mat_text in self.materials_map.items():
            attrs = parse_assembly_attributes(mat_text)
            self.assembly_attributes[tag] = attrs

        self.stage_timings["S05_assembly_attributes"] = round(time.time() - t0, 4)

    def _stage_s06_scale_calibration(self):
        """S06: Resolve architectural scale per floor plan page to compute ft_per_pt."""
        t0 = time.time()
        assert self.doc is not None
        self.page_scales = {}

        for p_idx, page in enumerate(self.doc):
            page_num = p_idx + 1
            ft_per_pt, matched_scale, status = detect_scale_from_page(page)
            self.page_scales[page_num] = ft_per_pt
            # Update sheet info
            self.sheets[p_idx]["scale_string"] = matched_scale
            self.sheets[p_idx]["scale_status"] = status
            self.sheets[p_idx]["ft_per_pt"] = round(ft_per_pt, 6)

        self.stage_timings["S06_scale_calibration"] = round(time.time() - t0, 4)
        print(f"[S06] Calibrated scale for {len(self.page_scales)} pages.")

    def _stage_s07_vector_extraction(self):
        """S07: Extract CAD straight vector segments and door swing arcs."""
        t0 = time.time()
        assert self.doc is not None
        self.page_linework = {}

        if self.selected_pages is not None:
            target_pages = [p for p in self.selected_pages if 1 <= p <= len(self.doc)]
        else:
            target_pages = [
                s["page_num"]
                for s in self.sheets
                if not (len(self.doc) > 1 and s.get("page_type") in ("PARTITION_SCHEDULE", "LEGEND", "COVER"))
            ] or [p + 1 for p in range(len(self.doc))]

        for page_num in target_pages:
            page = self.doc[page_num - 1]
            linework = extract_page_linework(page)
            self.page_linework[page_num] = linework

        total_segs = sum(len(lw.segments) for lw in self.page_linework.values())
        total_arcs = sum(len(lw.door_arcs) for lw in self.page_linework.values())
        self.stage_timings["S07_vector_extraction"] = round(time.time() - t0, 4)
        print(f"[S07] Extracted {total_segs} CAD segments and {total_arcs} door arcs across {len(target_pages)} pages.")

    def _stage_s08_tag_instances(self):
        """S08: Locate qualified drywall tag callouts on floor plan pages."""
        t0 = time.time()
        assert self.doc is not None
        self.tag_instances = []
        qualified_set = set(self.qualified_tags.keys())

        # If no qualified tags were found, use all discovered tags as fallback to ensure tracing proceeds
        if not qualified_set:
            qualified_set = set(self.discovered_tags)

        if self.selected_pages is not None:
            target_pages = [p for p in self.selected_pages if 1 <= p <= len(self.doc)]
        else:
            target_pages = [
                s["page_num"]
                for s in self.sheets
                if not (len(self.doc) > 1 and s.get("page_type") in ("PARTITION_SCHEDULE", "LEGEND", "COVER"))
            ] or [p + 1 for p in range(len(self.doc))]

        for page_num in target_pages:
            page = self.doc[page_num - 1]
            insts = find_tag_instances_on_page(page, qualified_set)
            self.tag_instances.extend(insts)

        self.stage_timings["S08_tag_instances"] = round(time.time() - t0, 4)
        print(f"[S08] Located {len(self.tag_instances)} qualified tag callouts on {len(target_pages)} sheets.")

    def _stage_s09_to_s12_wall_tracing(self):
        """S09-S12: Leader line detection, seed search, collinear chaining, opening deduction, spine generation."""
        t0 = time.time()
        self.raw_wall_runs = []
        run_counter = 1

        for tag_inst in self.tag_instances:
            page_num = tag_inst.page_num
            if self.selected_pages is not None and page_num not in self.selected_pages:
                continue
            linework = self.page_linework.get(page_num)
            if not linework or not linework.segments:
                continue

            ft_per_pt = self.page_scales.get(page_num, DEFAULT_FT_PER_PT)
            sheet_label = self.sheets[page_num - 1]["sheet_label"]

            # S09: Locate leader line endpoint pointing from tag to wall
            anchor_x, anchor_y, leader_seg = find_leader_endpoint(
                tc_x=tag_inst.center.x,
                tc_y=tag_inst.center.y,
                tag_radius=tag_inst.tag_radius,
                segments=linework.segments,
            )

            # S09: Locate nearest seed segment
            seed_seg = find_seed_segment(
                anchor_x=anchor_x,
                anchor_y=anchor_y,
                tc_x=tag_inst.center.x,
                tc_y=tag_inst.center.y,
                tag_radius=tag_inst.tag_radius,
                segments=linework.segments,
                leader_seg=leader_seg,
            )

            if seed_seg is None:
                continue

            # S10-S11: Trace wall segments & deduct openings
            run_id = f"RUN-{run_counter:03d}"
            traced = trace_wall_from_seed(
                seed_seg=seed_seg,
                leader_seg=leader_seg,
                segments=linework.segments,
                door_arcs=linework.door_arcs,
                ft_per_pt=ft_per_pt,
                page_num=page_num,
                wall_run_id=run_id,
            )

            if traced is not None:
                # S12: Centerline spine generation
                inst_id = f"TAG-{tag_inst.tag}-P{page_num}-{int(tag_inst.center.x)}_{int(tag_inst.center.y)}"
                tag_attrs = self.assembly_attributes.get(tag_inst.tag, {})
                wall_run = create_wall_run(
                    traced=traced,
                    tag=tag_inst.tag,
                    page_num=page_num,
                    sheet_label=sheet_label,
                    run_id=run_id,
                    ft_per_pt=ft_per_pt,
                    instance_id=inst_id,
                    assembly_attrs=tag_attrs,
                    material_layers=tag_attrs.get("material_layers"),
                )
                self.raw_wall_runs.append(wall_run)
                run_counter += 1

        self.stage_timings["S09_S12_wall_tracing"] = round(time.time() - t0, 4)
        print(f"[S09-S12] Traced {len(self.raw_wall_runs)} raw wall runs.")

    def _stage_s13_deduplication(self):
        """S13: Deduplicate overlapping runs and flag conflicting tags."""
        t0 = time.time()
        # Default scale for threshold conversion (prefer selected page)
        default_scale = DEFAULT_FT_PER_PT
        if self.selected_pages and self.page_scales.get(self.selected_pages[0], 0) > 0:
            default_scale = self.page_scales[self.selected_pages[0]]
        else:
            default_scale = self.page_scales.get(1, DEFAULT_FT_PER_PT)

        self.deduped_wall_runs = deduplicate_wall_runs(self.raw_wall_runs, default_scale)
        self.stage_timings["S13_deduplication"] = round(time.time() - t0, 4)
        print(f"[S13] Deduplicated into {len(self.deduped_wall_runs)} consolidated wall runs.")

    def _stage_s13b_section_height_verification(self):
        """S13B: Section callout tag discovery & wall height verification engine."""
        t0 = time.time()
        assert self.doc is not None
        from qto.section_heights import verify_wall_run_heights

        self.deduped_wall_runs, self.height_review_items = verify_wall_run_heights(
            doc=self.doc,
            wall_runs=self.deduped_wall_runs,
            sheet_catalog=self.sheets,
        )
        self.stage_timings["S13B_section_height_verification"] = round(time.time() - t0, 4)
        verified_count = sum(1 for r in self.deduped_wall_runs if getattr(r, "is_height_verified", False))
        print(
            f"[S13B] Height verification: {verified_count}/{len(self.deduped_wall_runs)} runs verified. "
            f"{len(self.height_review_items)} review items generated."
        )

    def _stage_s14_takeoff_quantities(self):
        """S14: Compute linear footage, board area, studs, track, and plates."""
        t0 = time.time()
        default_height_ft = float(self.config.get("default_height_ft", 10.0))
        stud_spacing_in = int(self.config.get("stud_spacing_in", 16))
        waste_percent = float(self.config.get("waste_percent", 0.0))

        scale_ft_per_pt = DEFAULT_FT_PER_PT
        if self.selected_pages and self.page_scales.get(self.selected_pages[0], 0) > 0:
            scale_ft_per_pt = self.page_scales[self.selected_pages[0]]
        else:
            scale_ft_per_pt = self.page_scales.get(1, DEFAULT_FT_PER_PT)

        any_default_scale = any(s.get("scale_status") == "DEFAULT_ASSUMED" for s in self.sheets)
        scale_status = "DEFAULT_ASSUMED" if any_default_scale else "MATCHED"

        self.takeoff_result = calculate_takeoff(
            runs=self.deduped_wall_runs,
            scale_ft_per_pt=scale_ft_per_pt,
            default_height_ft=default_height_ft,
            stud_spacing_in=stud_spacing_in,
            waste_percent=waste_percent,
            assembly_attributes=self.assembly_attributes,
            scale_status=scale_status,
            extra_review_items=self.height_review_items,
        )

        all_openings = []
        for r in self.deduped_wall_runs:
            for op in r.openings:
                all_openings.append(op.to_dict())
        self.openings_catalog = all_openings

        by_tag_dict = {}
        for tag, t_sum in self.takeoff_result.by_tag.items():
            by_tag_dict[tag] = t_sum.to_dict()

        target_processed = self.selected_pages or [s["page_num"] for s in self.sheets]
        self.takeoff_summary = {
            "run_id": self.run_id,
            "pdf_file": os.path.basename(self.pdf_path),
            "pdf_sha256": self.pdf_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "selected_pages": self.selected_pages,
            "sheets_processed": target_processed,
            "total_wall_runs": len(self.deduped_wall_runs),
            "total_openings_deducted": len(all_openings),
            "verified_height_count": sum(1 for r in self.deduped_wall_runs if getattr(r, "is_height_verified", False)),
            "unverified_height_count": sum(1 for r in self.deduped_wall_runs if not getattr(r, "is_height_verified", False)),
            "total_gross_lf": self.takeoff_result.total_gross_lf,
            "total_opening_deduction_lf": self.takeoff_result.total_opening_deduction_lf,
            "total_net_lf": self.takeoff_result.total_net_lf,
            "total_board_sf": self.takeoff_result.total_board_sf,
            "total_studs_ea": self.takeoff_result.total_studs_ea,
            "total_stud_lf": self.takeoff_result.total_stud_lf,
            "total_track_lf": self.takeoff_result.total_track_lf,
            "total_plates_lf": self.takeoff_result.total_plates_lf,
            "consumables": self.takeoff_result.consumables,
            "waste_percent": self.takeoff_result.waste_percent,
            "by_tag": by_tag_dict,
            "sheets": self.sheets,
            "openings": self.openings_catalog,
            "runs": [r.to_dict() for r in self.deduped_wall_runs],
            "assumptions": self.takeoff_result.assumptions,
            "review_items": self.takeoff_result.review_items,
            "lines": [l.to_dict() for l in self.takeoff_result.lines],
            "stage_timings": self.stage_timings,
        }

        self.stage_timings["S14_takeoff_quantities"] = round(time.time() - t0, 4)
        print(
            f"[S14] Computed takeoff quantities: Gross LF: {self.takeoff_result.total_gross_lf:.2f} | "
            f"Openings LF: {self.takeoff_result.total_opening_deduction_lf:.2f} | "
            f"Net LF: {self.takeoff_result.total_net_lf:.2f} | Board SF: {self.takeoff_result.total_board_sf:.2f}"
        )

    def _stage_s15_export_output(self):
        """S15: Export complete run data to runs/<run_id>/output.json and runs/<run_id>/qto.xlsx."""
        t0 = time.time()
        with open(self.output_json_path, "w", encoding="utf-8") as f:
            json.dump(self.takeoff_summary, f, indent=2)

        # Export 7-sheet openpyxl Excel workbook adhering to SOP 8.10.1
        export_takeoff_excel(
            takeoff=self.takeoff_result or self.takeoff_summary,
            run_info={
                "run_id": self.run_id,
                "pdf_file": os.path.basename(self.pdf_path),
                "pdf_sha256": self.pdf_hash,
                "timestamp": self.takeoff_summary.get("timestamp"),
                "default_height_ft": float(self.config.get("default_height_ft", 10.0)),
                "stud_spacing_in": int(self.config.get("stud_spacing_in", 16)),
            },
            output_path=self.qto_excel_path,
        )

        self.stage_timings["S15_export_output"] = round(time.time() - t0, 4)
        print(f"[S15] Saved execution JSON to {self.output_json_path}")
        print(f"[S15] Saved 7-sheet Excel workbook to {self.qto_excel_path}")

    def _stage_s16_annotate_pdf(self):
        """S16: Render dual-red visual vector drawings and interactive annotations."""
        t0 = time.time()
        annotate_blueprint_pdf(
            input_pdf_path=self.pdf_path,
            runs=self.deduped_wall_runs,
            tag_instances=self.tag_instances,
            output_pdf_path=self.annotated_pdf_path,
            registry=self.wall_registry,
        )
        self.stage_timings["S16_annotate_pdf"] = round(time.time() - t0, 4)
        print(f"[S16] Saved annotated PDF to {self.annotated_pdf_path}")


def run_pipeline(
    pdf_path: str,
    run_id: Optional[str] = None,
    output_dir: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience functional wrapper to execute the full QTO pipeline."""
    pipeline = QTOPipeline(pdf_path, run_id=run_id, output_dir=output_dir, config=config)
    return pipeline.run()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m qto.pipeline <path_to_blueprint_pdf>")
        sys.exit(1)

    target_pdf = sys.argv[1]
    result = run_pipeline(target_pdf)
    print(json.dumps(result, indent=2))

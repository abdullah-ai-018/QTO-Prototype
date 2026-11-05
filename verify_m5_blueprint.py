"""
Milestone 5 Real Blueprint Validation Script.
Validates real architectural blueprint wall detection, selective sheet processing,
dual-red visual annotations, and takeoff schedule calculation on:
  uploads/doc_20261104_101950_6cbd34.pdf
"""

import json
import os
import sys
import fitz
from qto.scale import detect_scale_from_page
from qto.segments import extract_page_linework
from qto.tags import find_tag_instances_on_page
from qto.trace_walls import find_leader_endpoint, find_seed_segment, trace_wall_from_seed
from qto.dedup import create_wall_run, deduplicate_wall_runs
from qto.quantities import calculate_takeoff
from qto.pipeline import QTOPipeline

pdf_path = "uploads/doc_20261104_101950_6cbd34.pdf"

print("=" * 70)
print(" MILESTONE 5: AUTHORITATIVE REAL BLUEPRINT VALIDATION")
print("=" * 70)
print(f"Target Blueprint: {pdf_path}")
assert os.path.exists(pdf_path), f"Blueprint not found: {pdf_path}"

# -----------------------------------------------------------------------------
# Part 1: Page 15 (Sheet A-101) Architectural Floor Plan Wall Detection
# -----------------------------------------------------------------------------
print("\n" + "-" * 70)
print(" [PART 1] Sheet A-101 (Page 15) Architectural Wall Detection Ground Truth")
print("-" * 70)
doc = fitz.open(pdf_path)
assert len(doc) == 71, f"Expected 71 pages, got {len(doc)}"
p15 = doc[14]

scale, scale_str, status = detect_scale_from_page(p15)
print(f"Page 15 Scale: {scale_str} (ft_per_pt = {scale:.6f}, status = {status})")
assert status == "DETECTED"
assert round(scale, 6) == 0.111111

lw15 = extract_page_linework(p15)
print(f"Page 15 Linework: {len(lw15.segments)} CAD segments, {len(lw15.door_arcs)} door arcs")
assert len(lw15.segments) == 5951, f"Expected 5951 segments, got {len(lw15.segments)}"
assert len(lw15.door_arcs) == 220, f"Expected 220 door arcs, got {len(lw15.door_arcs)}"

schedule_tags = {
    '0X', '1A', '1B', '1C', '1D', '1E', '2B', '2C', '2W', '2X', '3A', '3D',
    '4B1', '4K', '4P', '5B', '5D', '5E', '5L', '7A', '7B', '7C', '7E', '7F',
    '7G', '8A', '8P', 'GL1', 'GL2', 'PW'
}
insts15 = find_tag_instances_on_page(p15, schedule_tags)
print(f"Page 15 Tag Instances Located: {len(insts15)}")
assert len(insts15) == 31, f"Expected 31 tag instances, got {len(insts15)}"

raw_runs15 = []
for idx, tag_inst in enumerate(insts15):
    ax, ay, l_seg = find_leader_endpoint(tag_inst.center.x, tag_inst.center.y, tag_inst.tag_radius, lw15.segments)
    s_seg = find_seed_segment(ax, ay, tag_inst.center.x, tag_inst.center.y, tag_inst.tag_radius, lw15.segments, l_seg)
    if s_seg is None:
        continue
    traced = trace_wall_from_seed(s_seg, l_seg, lw15.segments, lw15.door_arcs, scale, 15, f"RUN-{idx+1:03d}")
    if traced:
        raw_runs15.append(create_wall_run(traced, tag_inst.tag, 15, "A-101", f"RUN-{idx+1:03d}", scale))

print(f"Page 15 Raw Wall Runs Traced: {len(raw_runs15)}")
assert len(raw_runs15) == 27, f"Expected 27 raw wall runs, got {len(raw_runs15)}"

deduped15 = deduplicate_wall_runs(raw_runs15, scale)
print(f"Page 15 Consolidated Wall Runs: {len(deduped15)}")
assert len(deduped15) == 19, f"Expected 19 consolidated runs, got {len(deduped15)}"

takeoff15 = calculate_takeoff(runs=deduped15, scale_ft_per_pt=scale)
print(f"Page 15 Takeoff Quantities:")
print(f"  Gross Linear Footage (LF): {takeoff15.total_gross_lf:.2f} (Target: ~495.83 LF)")
print(f"  Opening Deductions (LF):   {takeoff15.total_opening_deduction_lf:.2f} (Target: ~22.62 LF)")
print(f"  Net Linear Footage (LF):   {takeoff15.total_net_lf:.2f} (Target: ~473.21 LF)")
print(f"  Board Square Footage (SF): {takeoff15.total_board_sf:.2f} (Target: > 9,000 SF)")

assert abs(takeoff15.total_gross_lf - 495.83) < 2.0, f"Gross LF mismatch: {takeoff15.total_gross_lf}"
assert abs(takeoff15.total_net_lf - 473.21) < 2.0, f"Net LF mismatch: {takeoff15.total_net_lf}"
assert abs(takeoff15.total_opening_deduction_lf - 22.62) < 1.0, f"Deduction mismatch: {takeoff15.total_opening_deduction_lf}"
assert takeoff15.total_board_sf > 9000.0, f"Board SF mismatch: {takeoff15.total_board_sf}"
print("  => Page 15 (A-101) ground truth metrics VALIDATED successfully.")
doc.close()

# -----------------------------------------------------------------------------
# Part 2: Selective Sheet Processing on Sheet A-102 (Page 16) via QTOPipeline
# -----------------------------------------------------------------------------
print("\n" + "-" * 70)
print(" [PART 2] Selective Sheet Processing: Sheet A-102 (Page 16) via QTOPipeline")
print("-" * 70)
p16 = QTOPipeline(pdf_path, selected_pages=[16])
res16 = p16.run()

print(f"Page 16 Pipeline Results:")
print(f"  Sheets Processed:          {res16['sheets_processed']}")
print(f"  Consolidated Wall Runs:    {res16['total_wall_runs']}")
print(f"  Gross Linear Footage (LF): {res16['total_gross_lf']:.2f}")
print(f"  Opening Deductions (LF):   {res16['total_opening_deduction_lf']:.2f}")
print(f"  Net Linear Footage (LF):   {res16['total_net_lf']:.2f} (Target: ~340.01 LF)")
print(f"  Board Square Footage (SF): {res16['total_board_sf']:.2f} (Target: ~6,849.51 SF)")
print(f"  Annotated PDF Generated:   {p16.annotated_pdf_path}")

assert res16["sheets_processed"] == [16]
assert res16["total_wall_runs"] == 9, f"Expected 9 wall runs, got {res16['total_wall_runs']}"
assert abs(res16["total_net_lf"] - 340.01) < 1.0, f"Page 16 net LF mismatch: {res16['total_net_lf']}"
assert abs(res16["total_board_sf"] - 6849.51) < 5.0, f"Page 16 board SF mismatch: {res16['total_board_sf']}"

# Verify dual-red annotations generated in annotated.pdf for Page 16
doc16 = fitz.open(p16.annotated_pdf_path)
page16_annot = doc16[15]
annots16 = list(page16_annot.annots())
drawings16 = page16_annot.get_drawings()
print(f"  Page 16 PyMuPDF Annotations: {len(annots16)}")
print(f"  Page 16 Vector Drawings:     {len(drawings16)}")
assert len(annots16) > 0, "Page 16 missing annotations"
assert len(drawings16) > 0, "Page 16 missing dual-red vector linework"
doc16.close()
print("  => Page 16 (A-102) selective processing VALIDATED successfully.")

# -----------------------------------------------------------------------------
# Part 3: Selective Sheet Processing on Sheet A-101 (Page 15) via QTOPipeline
# -----------------------------------------------------------------------------
print("\n" + "-" * 70)
print(" [PART 3] Selective Sheet Processing: Sheet A-101 (Page 15) via QTOPipeline")
print("-" * 70)
p15_pipe = QTOPipeline(pdf_path, selected_pages=[15])
res15_pipe = p15_pipe.run()

print(f"Page 15 Pipeline Results:")
print(f"  Sheets Processed:          {res15_pipe['sheets_processed']}")
print(f"  Consolidated Wall Runs:    {res15_pipe['total_wall_runs']}")
print(f"  Gross Linear Footage (LF): {res15_pipe['total_gross_lf']:.2f}")
print(f"  Net Linear Footage (LF):   {res15_pipe['total_net_lf']:.2f}")
print(f"  Board Square Footage (SF): {res15_pipe['total_board_sf']:.2f}")
print(f"  Annotated PDF Generated:   {p15_pipe.annotated_pdf_path}")

assert res15_pipe["sheets_processed"] == [15]
assert res15_pipe["total_wall_runs"] == 5, f"Expected 5 wall runs, got {res15_pipe['total_wall_runs']}"
assert res15_pipe["total_gross_lf"] > 200.0
assert res15_pipe["total_net_lf"] > 200.0
assert res15_pipe["total_board_sf"] > 4000.0

# Verify dual-red annotations generated in annotated.pdf for Page 15
doc15_annot = fitz.open(p15_pipe.annotated_pdf_path)
page15_obj = doc15_annot[14]
annots15_pipe = list(page15_obj.annots())
drawings15_pipe = page15_obj.get_drawings()
print(f"  Page 15 PyMuPDF Annotations: {len(annots15_pipe)}")
print(f"  Page 15 Vector Drawings:     {len(drawings15_pipe)}")
assert len(annots15_pipe) > 0, "Page 15 missing annotations"
assert len(drawings15_pipe) > 0, "Page 15 missing dual-red vector linework"
doc15_annot.close()
print("  => Page 15 (A-101) selective processing VALIDATED successfully.")

# -----------------------------------------------------------------------------
# Part 4: Combined Selective Processing on Pages [15, 16] via QTOPipeline
# -----------------------------------------------------------------------------
print("\n" + "-" * 70)
print(" [PART 4] Combined Selective Processing: Pages [15, 16] via QTOPipeline")
print("-" * 70)
p_both = QTOPipeline(pdf_path, selected_pages=[15, 16])
res_both = p_both.run()

print(f"Combined [15, 16] Pipeline Results:")
print(f"  Sheets Processed:          {res_both['sheets_processed']}")
print(f"  Consolidated Wall Runs:    {res_both['total_wall_runs']}")
print(f"  Gross Linear Footage (LF): {res_both['total_gross_lf']:.2f}")
print(f"  Opening Deductions (LF):   {res_both['total_opening_deduction_lf']:.2f}")
print(f"  Net Linear Footage (LF):   {res_both['total_net_lf']:.2f}")
print(f"  Board Square Footage (SF): {res_both['total_board_sf']:.2f}")
print(f"  Annotated PDF Generated:   {p_both.annotated_pdf_path}")

expected_runs = res15_pipe["total_wall_runs"] + res16["total_wall_runs"]
expected_gross = res15_pipe["total_gross_lf"] + res16["total_gross_lf"]
expected_net = res15_pipe["total_net_lf"] + res16["total_net_lf"]
expected_sf = res15_pipe["total_board_sf"] + res16["total_board_sf"]

print(f"\nAggregation Mathematical Check:")
print(f"  Runs:  {res_both['total_wall_runs']} (Expected {expected_runs} = {res15_pipe['total_wall_runs']} + {res16['total_wall_runs']})")
print(f"  Gross: {res_both['total_gross_lf']:.2f} (Expected {expected_gross:.2f} = {res15_pipe['total_gross_lf']:.2f} + {res16['total_gross_lf']:.2f})")
print(f"  Net:   {res_both['total_net_lf']:.2f} (Expected {expected_net:.2f} = {res15_pipe['total_net_lf']:.2f} + {res16['total_net_lf']:.2f})")
print(f"  SF:    {res_both['total_board_sf']:.2f} (Expected {expected_sf:.2f} = {res15_pipe['total_board_sf']:.2f} + {res16['total_board_sf']:.2f})")

assert res_both["sheets_processed"] == [15, 16]
assert res_both["total_wall_runs"] == expected_runs
assert abs(res_both["total_gross_lf"] - expected_gross) < 0.05
assert abs(res_both["total_net_lf"] - expected_net) < 0.05
assert abs(res_both["total_board_sf"] - expected_sf) < 0.5
print("  => Combined selective processing [15, 16] VALIDATED successfully.")

print("\n" + "=" * 70)
print(" ALL MILESTONE 5 REAL BLUEPRINT VALIDATIONS PASSED CLEANLY!")
print("=" * 70)

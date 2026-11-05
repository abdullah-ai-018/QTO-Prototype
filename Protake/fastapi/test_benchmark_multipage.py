import json
from app.pdf.canonical_pipeline import CanonicalDrawingBuilder

pdf_path = "storage/pdf/5e2d48c7-3000-4f2d-9455-0e3e99b74bb4_Final Submission.pdf"
builder = CanonicalDrawingBuilder()
doc = builder.build_document(pdf_path)

print(f"==================================================")
print(f"BENCHMARK MULTI-PAGE AUDIT: {len(doc.pages)} PAGES DECODED")
print(f"==================================================")

for p in doc.pages:
    sc = p.scale_evidence
    scale_expr = sc.scale_string if sc else "None"
    scale_stat = sc.scale_status.value if (sc and hasattr(sc.scale_status, "value")) else (sc.scale_status if sc else "UNKNOWN")
    dtype = p.drawing_type.value if hasattr(p.drawing_type, "value") else str(p.drawing_type)
    
    print(f"\n--- PAGE {p.page_number} : {dtype} ---")
    print(f"Sheet: {p.sheet_number} | Title: {p.sheet_title}")
    print(f"Scale: {scale_expr} ({scale_stat}) | Units: {p.units}")
    print(f"Counts: Texts={len(p.text_objects)}, Vectors={len(p.geometry_objects)}, Dimensions={len(p.dimension_objects)}, Semantics={len(p.semantic_objects)}, Regions={len(p.regions)}")
    
    if p.regions:
        for r in p.regions:
            rtype = r.drawing_type.value if hasattr(r.drawing_type, "value") else str(r.drawing_type)
            print(f"  [Region] {r.region_id} | {r.title} | {rtype} | bbox={[round(x, 1) for x in r.bbox_pdf]}")
            
    if p.semantic_objects:
        type_counts = {}
        for so in p.semantic_objects:
            stype = so.object_type.value if hasattr(so.object_type, "value") else str(so.object_type)
            type_counts[stype] = type_counts.get(stype, 0) + 1
        print(f"  Semantic breakdown: {type_counts}")
        
    if p.takeoff_summary:
        ts = p.takeoff_summary
        tstatus = ts.gating_decision if hasattr(ts, "gating_decision") else (ts.overall_status.value if hasattr(ts.overall_status, "value") else str(ts.overall_status))
        print(f"  Takeoff Decision: {tstatus} | Drywall: {ts.drywall_sf} SF | Flooring: {ts.flooring_sf} SF | Roofing: {ts.roofing_sf} SF")
        for it in ts.items:
            istat = it.status.value if hasattr(it.status, "value") else str(it.status)
            print(f"    * [{it.trade}] {it.name}: {it.quantity} {it.unit} ({istat})")
            
    if p.cross_page_references:
        print(f"  Cross-Page References: {len(p.cross_page_references)}")
        for ref in p.cross_page_references:
            print(f"    -> Ref to Page {ref.target_page} ({ref.reference_type}): {ref.marker_text} - {ref.description}")

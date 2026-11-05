import glob
from app.pdf.canonical_pipeline import CanonicalDrawingBuilder

files = glob.glob("storage/pdf/*Final Submission*.pdf")
pdf_path = files[0]
print("Processing PDF:", pdf_path)

builder = CanonicalDrawingBuilder()
doc = builder.build_document(pdf_path, target_page_num=None)

print(f"\nDocument Processed: {doc.document_id}, Page count: {len(doc.pages)}")
for p in doc.pages:
    print(f"\n--- PAGE {p.page_number} ---")
    print(f"Sheet: {p.sheet_number} | Title: {p.sheet_title}")
    print(f"Drawing Type: {p.drawing_type.value} | Discipline: {p.discipline}")
    print(f"Regions: {len(p.regions)} | Text: {len(p.text_objects)} | Vectors: {len(p.geometry_objects)}")
    print(f"Dimensions: {len(p.dimension_objects)} | Semantic Objects: {len(p.semantic_objects)}")
    print(f"Scale: {p.scale_evidence.scale_string} ({p.scale_evidence.scale_status.value})")
    print(f"Takeoff gating: {p.takeoff_summary.gating_decision if p.takeoff_summary else 'N/A'}")
    print(f"Validation: {p.validation_report.validation_state if p.validation_report else 'N/A'}")
    if p.takeoff_summary:
        print(f"  Drywall: {p.takeoff_summary.drywall_sf} SF ({p.takeoff_summary.drywall_status})")
        print(f"  Flooring: {p.takeoff_summary.flooring_sf} SF ({p.takeoff_summary.flooring_status})")
        print(f"  Roofing: {p.takeoff_summary.roofing_sf} SF ({p.takeoff_summary.roofing_status})")

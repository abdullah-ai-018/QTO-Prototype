import fitz
from app.pdf.vector_extractor import PDFVectorExtractor
from app.pdf.content_extractor import PDFContentExtractor
from app.pdf.scale_validator import ScaleValidator
from app.pdf.roof_classifier import RoofVectorClassifier
from app.pdf.roof_topology import RoofTopologyReconstructor

doc = fitz.open("storage/pdf/5e2d48c7-3000-4f2d-9455-0e3e99b74bb4_Final Submission.pdf")
ve = PDFVectorExtractor()
ce = PDFContentExtractor()
sv = ScaleValidator()
rc = RoofVectorClassifier()
rt = RoofTopologyReconstructor()

print("=== PAGE 1 (DETAIL DRAWING - COOKING HOOD / CABINET) ===")
p1 = doc[0]
p1_geoms = ve.extract_page_vectors(p1, 1)
p1_texts = ce.extract_page_content(p1, 1)
p1_scale = sv.validate_page_scale(p1_texts, p1_geoms)
p1_class = rc.classify_page_vectors(p1_geoms, p1_texts, p1.rect.width, p1.rect.height)
p1_roof = rt.reconstruct_sheet_roof(p1_class, p1_texts, p1_scale, 1)
print("Page 1 Scale Status:", p1_scale.scale_status.value)
print("Page 1 Scale String:", p1_scale.scale_string)
print("Page 1 Roof Planes Count:", len(p1_roof.planes))
print("Page 1 Plan Area SF:", p1_roof.total_plan_area_sqft)
print("Page 1 True Surface Area SF:", p1_roof.total_true_surface_area_sqft)
print("Page 1 Classified Roof Boundaries:", len(p1_class.roof_boundaries))
print("Page 1 Classified Title Block Lines:", len(p1_class.title_block_lines))

print("\n=== PAGE 6 (TOP ROOF WORKING PLAN) ===")
p6 = doc[5]
p6_geoms = ve.extract_page_vectors(p6, 6)
p6_texts = ce.extract_page_content(p6, 6)
p6_scale = sv.validate_page_scale(p6_texts, p6_geoms)
p6_class = rc.classify_page_vectors(p6_geoms, p6_texts, p6.rect.width, p6.rect.height)
p6_roof = rt.reconstruct_sheet_roof(p6_class, p6_texts, p6_scale, 6)
print("Page 6 Scale Status:", p6_scale.scale_status.value)
print("Page 6 Scale String:", p6_scale.scale_string)
print("Page 6 Roof Planes Count:", len(p6_roof.planes))
print("Page 6 Plan Area SF:", p6_roof.total_plan_area_sqft)
print("Page 6 True Surface Area SF:", p6_roof.total_true_surface_area_sqft)

print("\n=== SAMPLE COMMERCIAL ROOF (PAGE 11) ===")
doc2 = fitz.open("../frontend/public/sample/commercial_sample.pdf")
p11 = doc2[10]
p11_geoms = ve.extract_page_vectors(p11, 11)
p11_texts = ce.extract_page_content(p11, 11)
p11_scale = sv.validate_page_scale(p11_texts, p11_geoms)
p11_class = rc.classify_page_vectors(p11_geoms, p11_texts, p11.rect.width, p11.rect.height)
p11_roof = rt.reconstruct_sheet_roof(p11_class, p11_texts, p11_scale, 11)
print("Page 11 Scale Status:", p11_scale.scale_status.value)
print("Page 11 Scale String:", p11_scale.scale_string)
print("Page 11 Roof Planes Count:", len(p11_roof.planes))
print("Page 11 Plan Area SF:", p11_roof.total_plan_area_sqft)
print("Page 11 True Surface Area SF:", p11_roof.total_true_surface_area_sqft)
for idx, pl in enumerate(p11_roof.planes):
    print(f"  Plane {idx+1}: {pl.name}, area_sqft={pl.plan_area_sqft}, true_sqft={pl.true_surface_area_sqft}, pts={pl.boundary_points_pdf}")

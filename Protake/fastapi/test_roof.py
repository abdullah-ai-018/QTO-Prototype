import glob
from app.pdf.content_extractor import PDFContentExtractor
from app.pdf.vector_extractor import PDFVectorExtractor
from app.pdf.scale_validator import ScaleValidator
from app.pdf.roof_classifier import RoofVectorClassifier
from app.pdf.roof_topology import RoofTopologyReconstructor
import fitz

files = glob.glob("storage/pdf/*Final Submission*.pdf")
doc = fitz.open(files[0])
page = doc[5] # Page 6 (0-indexed 5)

content_ext = PDFContentExtractor()
vector_ext = PDFVectorExtractor()
scale_val = ScaleValidator()
roof_cls = RoofVectorClassifier()
topology_rec = RoofTopologyReconstructor()

texts = content_ext.extract_page_content(page, 6)
vectors = vector_ext.extract_page_vectors(page, 6)
scale = scale_val.validate_page_scale(texts, vectors)
print(f"Scale: {scale.scale_string} ({scale.scale_status.value})")

classified = roof_cls.classify_page_vectors(vectors, texts, page.rect.width, page.rect.height)
print(f"Classified vectors: boundary={len(classified.boundary_loops)}, ridge={len(classified.ridge_vectors)}, hip={len(classified.hip_vectors)}, valley={len(classified.valley_vectors)}")

summary = topology_rec.reconstruct_sheet_roof(classified, texts, scale, page_number=6)
print(f"Planes found: {len(summary.planes)}")
print(f"Total plan area: {summary.total_plan_area_sqft} sqft")
print(f"Total true surface area: {summary.total_true_surface_area_sqft} sqft")
for p in summary.planes:
    print(f"  Plane {p.plane_id}: area={p.plan_area_sqft:.2f} sqft, pitch={p.pitch}")

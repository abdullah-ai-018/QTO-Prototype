import glob
import fitz
from app.pdf.content_extractor import PDFContentExtractor
from app.pdf.vector_extractor import PDFVectorExtractor

files = glob.glob("storage/pdf/*Final Submission*.pdf")
doc = fitz.open(files[0])
page = doc[5] # Page 6

ce = PDFContentExtractor()
ve = PDFVectorExtractor()

texts = ce.extract_page_content(page, 6)
vectors = ve.extract_page_vectors(page, 6)

print(f"Total texts: {len(texts)}")
print(f"Total vectors: {len(vectors)}")

closed_vecs = [g for g in vectors if g.is_closed]
print(f"Closed vectors count: {len(closed_vecs)}")

for i, g in enumerate(closed_vecs[:20]):
    pts = g.source_points_pdf
    w = g.bbox_pdf[2] - g.bbox_pdf[0]
    h = g.bbox_pdf[3] - g.bbox_pdf[1]
    print(f"  Closed vec {i+1}: pts={len(pts)}, bbox={[round(x,1) for x in g.bbox_pdf]}, w={w:.1f}, h={h:.1f}")

# Look for large line segments that form the roof boundary
lines = [g for g in vectors if not g.is_closed and len(g.source_points_pdf) >= 2]
print(f"Open linework count: {len(lines)}")
large_lines = [g for g in lines if (g.bbox_pdf[2]-g.bbox_pdf[0]) > 50 or (g.bbox_pdf[3]-g.bbox_pdf[1]) > 50]
print(f"Large lines (>50pt): {len(large_lines)}")
for i, g in enumerate(large_lines[:15]):
    pts = g.source_points_pdf
    print(f"  Line {i+1}: pts={pts}, bbox={[round(x,1) for x in g.bbox_pdf]}")

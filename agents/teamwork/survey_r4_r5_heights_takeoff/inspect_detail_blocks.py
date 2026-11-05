import fitz
import re

doc = fitz.open("uploads/doc_20261104_101950_6cbd34.pdf")
p15 = doc[14]

blocks = p15.get_text("blocks")
print(f"Total text blocks on Page 15: {len(blocks)}")

# Find blocks containing sheet references like A-7xx, A-8xx, A-9xx, A-3xx, A-4xx
detail_blocks = []
for b in blocks:
    txt = b[4].strip()
    if re.search(r"\bA-[2-9]\d{2}\b", txt):
        detail_blocks.append(b)

print(f"\nFound {len(detail_blocks)} detail reference blocks on Page 15:")
for b in detail_blocks:
    print(f"BBox: ({b[0]:.1f}, {b[1]:.1f}, {b[2]:.1f}, {b[3]:.1f}) | Text: {repr(b[4].strip())}")

# Also let's check what drawings/vectors are near these blocks
print("\n--- Let's inspect drawing shapes near the first 5 detail callouts ---")
drawings = p15.get_drawings()
for b in detail_blocks[:5]:
    bx0, by0, bx1, by1 = b[:4]
    nearby_drawings = []
    for d in drawings:
        r = d.get("rect")
        if r and (abs(r.x0 - bx0) < 30 and abs(r.y0 - by0) < 30):
            nearby_drawings.append(d)
    print(f"Detail block {repr(b[4].strip())} at ({bx0:.1f}, {by0:.1f}) has {len(nearby_drawings)} nearby drawing paths.")
    for nd in nearby_drawings[:3]:
        print(f"   item types: {[it[0] for it in nd.get('items', [])]}")

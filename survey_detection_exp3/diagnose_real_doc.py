import fitz
import re
from qto.scale import detect_scale_from_page
from qto.tags import discover_tags_from_schedules, find_tag_instances_on_page
from qto.segments import extract_page_linework

doc = fitz.open("uploads/doc_20261104_101950_6cbd34.pdf")
print(f"Total pages: {len(doc)}")

# 1. Schedule tag discovery
print("\n--- 1. Schedule Tag Discovery ---")
discovered_tags = discover_tags_from_schedules(doc)
print(f"Discovered tags from schedules: {discovered_tags}")

# 2. Inspect partition schedule pages: A-900 (p63, idx 62) and A-901 (p64, idx 63)
for pnum in [63, 64]:
    p = doc[pnum - 1]
    txt = p.get_text()
    tags = re.findall(r"\b([0-9][A-Z]|[1-9][A-Z][0-9]|GL[1-9]|PW)\b", txt)
    # also search for partition patterns like 1A, 2B, 3C, P-1, etc.
    other_tags = re.findall(r"\b([0-9]{1,2}[A-Z]{1,2}|P[-_]?[0-9A-Z]+)\b", txt)
    print(f"Page {pnum} text length: {len(txt)}, regex matches: {set(tags)}, other_tags: {set(other_tags)[:10]}")

# 3. Floor plan analysis: Page 15 (A-101 First Floor Construction Plan)
print("\n--- 2. Floor Plan Analysis (Page 15, Sheet A-101) ---")
p15 = doc[14]
scale_res = detect_scale_from_page(p15)
print(f"Page 15 scale detection: {scale_res}")

linework15 = extract_page_linework(p15)
print(f"Page 15 extracted linework: {len(linework15.segments)} segments, {len(linework15.door_arcs)} door arcs")

words15 = p15.get_text("words")
print(f"Page 15 total words: {len(words15)}")
matching_words = [w for w in words15 if re.match(r"^([0-9][A-Z]|[1-9][A-Z][0-9]|GL[1-9]|PW)$", w[4])]
print(f"Page 15 words matching TAG_REGEX: {[w[4] for w in matching_words]}")

# 4. Check drawings on Page 15
drawings15 = p15.get_drawings()
print(f"Page 15 get_drawings count: {len(drawings15)}")

# 5. Check what actual wall lines look like on Page 15
# Are walls drawn as double parallel lines? What thicknesses?
print("\n--- 3. Page 15 Vector segment statistics ---")
if linework15.segments:
    lens = [s.length for s in linework15.segments]
    print(f"Segment length min={min(lens):.1f}, max={max(lens):.1f}, avg={sum(lens)/len(lens):.1f}")
    # Count horizontal vs vertical
    h_segs = [s for s in linework15.segments if abs(s.y2 - s.y1) < 1.0]
    v_segs = [s for s in linework15.segments if abs(s.x2 - s.x1) < 1.0]
    print(f"Horizontal segs: {len(h_segs)}, Vertical segs: {len(v_segs)}")

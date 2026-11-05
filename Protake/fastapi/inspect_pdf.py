import glob
import re
import fitz

files = glob.glob("storage/pdf/*Final Submission*.pdf")
if not files:
    print("No Final Submission.pdf found!")
    exit(1)

doc = fitz.open(files[0])
print(f"Total pages: {len(doc)}")

for p_num in range(len(doc)):
    page = doc[p_num]
    text = page.get_text()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    dims = []
    for l in lines:
        if "'" in l or '"' in l or "mm" in l or re.search(r"\d+[-']\d+", l):
            dims.append(l)
    print(f"Page {p_num+1} Dimension/Length text candidates ({len(dims)} total):")
    print("   ", dims[:15])

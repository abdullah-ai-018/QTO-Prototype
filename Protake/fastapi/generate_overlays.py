import fitz
from PIL import Image, ImageDraw, ImageFont
import math
import re
import os

pdf_path = 'storage/pdf/14dba04c-6b98-461a-95c8-504cf6ef4d47_5e2d48c7-3000-4f2d-9455-0e3e99b74bb4_Final Submission.pdf'
doc = fitz.open(pdf_path)

out_dir = r'C:\Users\lenovo\.gemini\antigravity-ide\brain\8183e42b-8863-456a-bcb8-4db9fb72819f'
os.makedirs(out_dir, exist_ok=True)

for pno, pname in [(7, 'page_7_first_floor_overlay.png'), (8, 'page_8_ground_floor_overlay.png')]:
    page = doc[pno - 1]
    zoom = 2.0  # 144 DPI
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    
    # Convert to PIL Image
    base_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("RGBA")
    overlay = Image.new("RGBA", base_img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    
    # 1. Overlay Drawing Grids & Walls
    # We can parse the drawing paths from page
    paths = page.get_drawings()
    for p in paths:
        stroke_color = p.get('color')
        items = p['items']
        for it in items:
            cmd = it[0]
            if cmd == 'l':
                p1, p2 = it[1], it[2]
                length = math.hypot(p2.x - p1.x, p2.y - p1.y)
                # Wall line candidates
                if length >= 25.0:
                    draw.line([p1.x * zoom, p1.y * zoom, p2.x * zoom, p2.y * zoom], fill=(220, 20, 60, 180), width=2)
                elif 8.0 <= length < 25.0:
                    # Windows or opening frames
                    draw.line([p1.x * zoom, p1.y * zoom, p2.x * zoom, p2.y * zoom], fill=(255, 140, 0, 160), width=2)
            elif cmd == 'c':
                # Door swing arcs
                # sample bezier
                p1, p2, p3, p4 = it[1], it[2], it[3], it[4]
                pts = []
                for step in range(11):
                    t = step / 10.0
                    bx = (1-t)**3 * p1.x + 3*(1-t)**2 * t * p2.x + 3*(1-t)*t**2 * p3.x + t**3 * p4.x
                    by = (1-t)**3 * p1.y + 3*(1-t)**2 * t * p2.y + 3*(1-t)*t**2 * p3.y + t**3 * p4.y
                    pts.append((bx * zoom, by * zoom))
                draw.line(pts, fill=(34, 139, 34, 220), width=3)
    
    # 2. Overlay Rooms
    blocks = page.get_text('blocks')
    for b in blocks:
        txt = b[4].strip().replace('\n', ' ')
        m = re.search(r'([A-Z\.\s]+?)\s+(\d+[\'-][^\s]+)\s*[xX]\s*(\d+[\'-][^\s]+)', txt)
        if m:
            rname = m.group(1).strip()
            # Draw semi-transparent room badge / box
            bx0, by0, bx1, by1 = b[0] * zoom, b[1] * zoom, b[2] * zoom, b[3] * zoom
            pad = 12 * zoom
            draw.rectangle([bx0 - pad, by0 - pad, bx1 + pad, by1 + pad], fill=(30, 144, 255, 60), outline=(0, 102, 204, 200), width=2)
            draw.text((bx0 - pad, by0 - pad - 12), f"ROOM: {rname}", fill=(0, 51, 153, 255))
    
    # 3. Legend on the overlay
    leg_x, leg_y = 40, 40
    leg_items = [
        ("WALLS (Structural Linework)", (220, 20, 60, 255)),
        ("DOORS (Swing Arcs)", (34, 139, 34, 255)),
        ("WINDOWS / OPENINGS", (255, 140, 0, 255)),
        ("ROOMS (Classified Enclosures)", (0, 102, 204, 255)),
    ]
    draw.rectangle([leg_x - 10, leg_y - 10, leg_x + 320, leg_y + len(leg_items)*25 + 10], fill=(255, 255, 255, 220), outline=(100, 100, 100, 255), width=2)
    draw.text((leg_x, leg_y - 5), f"SEMANTIC OVERLAY: PAGE {pno}", fill=(0, 0, 0, 255))
    for idx, (label, col) in enumerate(leg_items):
        ly = leg_y + 20 + idx * 22
        draw.rectangle([leg_x, ly + 2, leg_x + 20, ly + 16], fill=col)
        draw.text((leg_x + 30, ly), label, fill=(0, 0, 0, 255))
    
    # Composite overlay over original base image
    final_img = Image.alpha_composite(base_img, overlay)
    out_path = os.path.join(out_dir, pname)
    final_img.save(out_path, format="PNG")
    print(f"Generated overlay for Page {pno}: {out_path} ({final_img.width}x{final_img.height})")

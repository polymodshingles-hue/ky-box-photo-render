#!/usr/bin/env python3
"""One-time: seed site/projects/catalog.json from the PORTFOLIO list in build_pages.py. Run from site/."""
import ast, re, json, os, datetime
src = open('build_pages.py', encoding='utf-8').read()
body = src[src.index('PORTFOLIO = [') + len('PORTFOLIO = '):src.index('\nchips_i')]
body = re.sub(r'#[^\n]*', '', body)
P = ast.literal_eval(body.strip())
def slug(t): return re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')
def fin(c):
    c = c.lower(); out = []
    if 'foil' in c: out.append('foil')
    if 'emboss' in c or 'deboss' in c: out.append('emboss')
    if 'window' in c: out.append('window')
    return out
TAX = {
 "industries": {
  "religious": {"label": "Religious & Publishing", "pages": ["custom-religious-packaging", "custom-book-slipcases"]},
  "gaming": {"label": "Gaming & Entertainment", "pages": ["custom-gaming-box-set", "custom-board-game-boxes-tabletop-packaging"]},
  "retail": {"label": "Retail & Gifts", "pages": ["custom-retail-packaging", "corporate-gift-boxes"]},
  "beauty": {"label": "Health & Beauty", "pages": ["custom-cosmetic-rigid-boxes"]},
  "spirits": {"label": "Wine & Spirits", "pages": ["custom-spirits-packaging", "custom-bourbon-whiskey-boxes"]},
  "chocolates": {"label": "Chocolates", "pages": ["custom-chocolate-boxes"]},
  "pharma": {"label": "Pharmaceutical", "pages": ["custom-pharmaceutical-packaging"]},
  "jewelry": {"label": "Jewelry & Watches", "pages": ["custom-jewelry-watch-boxes"]},
  "automotive": {"label": "Automotive", "pages": ["custom-automotive-packaging"]},
  "cannabis": {"label": "Cannabis & CBD", "pages": ["custom-cannabis-packaging"]}
 },
 "styles": {
  "two-piece": {"label": "Two-Piece", "url": "/two-piece-rigid-boxes/", "pages": ["two-piece-rigid-boxes"]},
  "neck": {"label": "Neck", "url": "/three-piece-neck-boxes/", "pages": ["three-piece-neck-boxes"]},
  "book-style": {"label": "Book-Style", "url": "/book-style-rigid-boxes/", "pages": ["book-style-rigid-boxes"]},
  "clamshell": {"label": "Clamshell", "url": "/clamshell-rigid-boxes/", "pages": ["clamshell-rigid-boxes"]},
  "slipcase": {"label": "Slipcase", "url": "/slipcase-drawer-rigid-boxes/", "pages": ["slipcase-drawer-rigid-boxes", "custom-book-slipcases"]},
  "drawer": {"label": "Drawer", "url": "/slipcase-drawer-rigid-boxes/", "pages": ["slipcase-drawer-rigid-boxes"]},
  "magnetic": {"label": "Magnetic Closure", "url": "/magnetic-closure-rigid-boxes/", "pages": ["magnetic-closure-rigid-boxes"]},
  "die-cut": {"label": "Die Cuts & Windows", "url": "/value-added-services/", "pages": ["value-added-services", "rigid-box-die-cutting"]},
  "insert": {"label": "Inserts", "url": "/custom-rigid-box-inserts/", "pages": ["custom-rigid-box-inserts"]}
 },
 "finishes": {
  "foil": {"label": "Foil stamping", "pages": ["foil-stamping-rigid-boxes"]},
  "emboss": {"label": "Embossing & debossing", "pages": ["embossing-and-debossing"]},
  "window": {"label": "Die-cut windows", "pages": ["rigid-box-die-cutting"]},
  "soft-touch": {"label": "Soft-touch", "pages": ["soft-touch-rigid-boxes"]}
 }
}
projects, seen = [], set()
for n, ind, sty, cap in P:
    src_ = n if n.startswith('/') else f'/images/work/{n}.jpg'
    s = slug(cap)
    while s in seen: s += '-2'
    seen.add(s)
    projects.append({"slug": s, "title": cap, "industry": ind, "styles": [sty], "finishes": fin(cap), "brand_ok": True,
                     "photos": [{"src": src_, "role": "hero", "alt": cap}], "notes": "", "source": "ported from the old kybox.com",
                     "added": "2026-11-18"})
os.makedirs('projects', exist_ok=True)
json.dump({"_readme": "Single source for every real project photo on the site. Edited by Claude after each photo-booth batch. build_pages.py (portfolio) and build_gallery.py (strips on style/industry/finish pages) read it.",
           "taxonomy": TAX, "projects": projects}, open('projects/catalog.json', 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
print('seeded', len(projects))

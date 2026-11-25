#!/usr/bin/env python3
"""Photo-booth batch processor (2026-11-18). Run from 'ky box':  python3 site/tools/process_photos.py photo-inbox/<batch>/batch.json

Claude writes batch.json after looking at the raw photos:
{
 "projects": [
  {"slug": "bourbon-truffle-two-piece", "title": "Bourbon truffle box with gold foil", "industry": "chocolates",
   "styles": ["two-piece"], "finishes": ["foil"], "brand_ok": true, "notes": "customer OK'd by Mike 11/20",
   "photos": [
     {"raw": "PXL_20261120_1301.jpg", "role": "hero", "alt": "Two-piece bourbon truffle box, gold foil lid"},
     {"raw": "PXL_20261120_1302.jpg", "role": "open", "alt": "...", "crop": [0.1, 0.05, 0.9, 0.95], "rotate": 0}
   ]}
 ]
}
For each photo: fix phone rotation, white-balance to the booth's white backdrop, trim to the box with a margin
(or use "crop" as fractions l,t,r,b), sharpen lightly, 2000 px on the long side, then save
site/images/projects/<slug>/<slug>-<nn>-<role>.jpg + .webp. The catalog entry in site/projects/catalog.json is added
or replaced. Raw files are never changed. build_perf.py makes the 480/800 copies on the next chain run."""
import sys, os, json, datetime
from PIL import Image, ImageOps, ImageFilter, ImageChops, ImageStat

LONG = 2000
ROLES = ['hero', 'open', 'insert', 'detail', 'scale', 'flat', 'spin', 'extra']

def border_mean(im, band=0.04):
    w, h = im.size; b = max(4, int(min(w, h) * band))
    boxes = [(0, 0, w, b), (0, h - b, w, h), (0, 0, b, h), (w - b, 0, w, h)]
    px = [ImageStat.Stat(im.crop(bx)).mean for bx in boxes]
    return [sum(c[i] for c in px) / 4 for i in range(3)]

def white_balance(im):
    """Scale channels so the backdrop reads neutral near-white. Gains clamped so a non-white backdrop isn't wrecked."""
    r, g, b = border_mean(im)
    target = 243
    gains = [min(1.45, max(0.8, target / max(c, 1))) for c in (r, g, b)]
    ch = [c.point(lambda v, k=k: min(255, int(v * k))) for c, k in zip(im.split(), gains)]
    return Image.merge('RGB', ch)

def auto_trim(im, pad=0.08):
    bg = Image.new('RGB', im.size, tuple(int(c) for c in border_mean(im)))
    diff = ImageChops.difference(im, bg).convert('L').point(lambda v: 255 if v > 28 else 0)
    diff = diff.filter(ImageFilter.MedianFilter(5))
    box = diff.getbbox()
    if not box: return im
    w, h = im.size; l, t, r, b = box
    if (r - l) * (b - t) < 0.05 * w * h: return im   # found specks, not a box: leave the frame alone
    px, py = int((r - l) * pad), int((b - t) * pad)
    return im.crop((max(0, l - px), max(0, t - py), min(w, r + px), min(h, b + py)))

def process(raw, out_base, crop=None, rotate=0, wb=True):
    im = ImageOps.exif_transpose(Image.open(raw)).convert('RGB')
    if rotate: im = im.rotate(-rotate, expand=True, fillcolor=(255, 255, 255))
    if wb: im = white_balance(im)
    if crop:
        w, h = im.size; im = im.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
    else:
        im = auto_trim(im)
    k = LONG / max(im.size)
    if k < 1: im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    im.save(out_base + '.jpg', 'JPEG', quality=85, optimize=True, progressive=True)
    im.save(out_base + '.webp', 'WEBP', quality=80, method=6)
    return im.size

def main(batch_path):
    root = os.path.dirname(os.path.abspath(batch_path))
    site = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
    B = json.load(open(batch_path, encoding='utf-8'))
    catp = os.path.join(site, 'projects', 'catalog.json')
    cat = json.load(open(catp, encoding='utf-8'))
    tax = cat['taxonomy']
    for p in B['projects']:
        assert p['industry'] in tax['industries'], f"unknown industry {p['industry']} (add it to the catalog taxonomy first)"
        for s in p['styles']: assert s in tax['styles'], f'unknown style {s}'
        for f in p.get('finishes', []): assert f in tax['finishes'], f'unknown finish {f}'
        d = os.path.join(site, 'images', 'projects', p['slug']); os.makedirs(d, exist_ok=True)
        photos = []
        for i, ph in enumerate(p['photos'], 1):
            role = ph.get('role', 'extra'); assert role in ROLES, role
            name = f"{p['slug']}-{i:02d}-{role}"
            size = process(os.path.join(root, ph['raw']), os.path.join(d, name), ph.get('crop'), ph.get('rotate', 0), ph.get('wb', True))
            photos.append({'src': f"/images/projects/{p['slug']}/{name}.jpg", 'role': role, 'alt': ph.get('alt') or p['title'],
                           'w': size[0], 'h': size[1], 'raw': ph['raw']})
            print('  ', name, size)
        entry = {k: p.get(k) for k in ('slug', 'title', 'industry', 'styles', 'finishes', 'brand_ok', 'notes')}
        entry.update(photos=photos, source='photo booth', added=datetime.date.today().isoformat())
        if not entry['brand_ok']: print(f"   NOTE {p['slug']}: brand_ok is false; check no customer logo shows in the photos")
        cat['projects'] = [x for x in cat['projects'] if x['slug'] != p['slug']] + [entry]
    json.dump(cat, open(catp, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f"catalog: {len(cat['projects'])} projects")

if __name__ == '__main__':
    main(sys.argv[1])

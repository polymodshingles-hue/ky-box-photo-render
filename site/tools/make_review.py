#!/usr/bin/env python3
"""Builds _work/processed/review_<n>.jpg: contact sheets of finished photos for a visual check, with the QC text under each.
Run from the 'ky box' folder:  python3 site/tools/make_review.py"""
import os, json, glob
from PIL import Image, ImageDraw
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')); OUT = os.path.join(ROOT, '_work', 'processed')
rep = json.load(open(os.path.join(OUT, 'report.json'))); items = [(k, v) for k, v in sorted(rep.items()) if v.get('status') == 'done']
T = 380; cols = 5; per = 15
for n in range(0, len(items), per):
    ch = items[n:n+per]; rows = (len(ch)+cols-1)//cols; sh = Image.new('RGB', (cols*T, rows*(T+30)), 'white'); d = ImageDraw.Draw(sh)
    for i, (k, v) in enumerate(ch):
        proj, name = k.split('/'); _f = os.path.join(OUT, proj, os.path.splitext(name)[0] + '.jpg')
        if not os.path.exists(_f): continue
        im = Image.open(_f); im.thumbnail((T, T))
        x, y = (i % cols)*T, (i//cols)*(T+30); sh.paste(im, (x, y)); d.text((x+3, y+T+1), f"{proj[:22]} | {os.path.splitext(name)[0][-14:]}", fill='black')
        d.text((x+3, y+T+13), f"{v['cutout']} | {'OK' if v['qc_ok'] else 'CHECK: '+v['qc']}", fill='red' if not v['qc_ok'] else 'green')
    p = os.path.join(OUT, f'review_{n//per+1}.jpg'); sh.save(p, quality=86); print(p)

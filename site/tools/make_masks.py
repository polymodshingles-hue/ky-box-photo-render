#!/usr/bin/env python3
"""Pre-computes AI cutout masks (isnet-general-use via rembg) into _work/masks/<project>/<stem>.png for every photo listed in _work/meta.
Run by Claude whenever new photos are filed; the workhorse does NOT need rembg because post_edit.py just reads these cached masks.
Resumable. Usage: python make_masks.py [project ...]"""
import os, sys, json, glob
os.environ.setdefault('U2NET_HOME', os.path.expanduser('~/models'))
import numpy as np
from PIL import Image, ImageOps
from rembg import new_session, remove
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')); META = os.path.join(ROOT, '_work', 'meta')
s = new_session('isnet-general-use'); only = set(sys.argv[1:]); done = 0; import time; t0 = time.time()
for mp in sorted(glob.glob(os.path.join(META, '*.json'))):
    m = json.load(open(mp, encoding='utf-8')); slug = m['slug']
    if only and slug not in only: continue
    for ph in m['photos']:
        src = os.path.join(ROOT, 'PHOTOS', '1-ORIGINALS', slug, ph['file']); out = os.path.join(ROOT, '_work', 'masks', slug, os.path.splitext(ph['file'])[0]+'.png')
        if not os.path.exists(src): continue
        if os.path.exists(out) and os.stat(out).st_mtime_ns >= os.stat(src).st_mtime_ns: continue      # remake when the photo was replaced after its mask
        if time.time()-t0 > 150: print('time budget reached; run again'); sys.exit(2)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        im = ImageOps.exif_transpose(Image.open(src)).convert('RGB'); im.thumbnail((1600, 1600))
        remove(im, session=s, only_mask=True).save(out + '.tmp.png'); os.replace(out + '.tmp.png', out); done += 1
print('masks made:', done)

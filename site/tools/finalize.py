#!/usr/bin/env python3
"""Turns finished edits into spec-named deliverables.  _work/processed/<project>/  ->  PHOTOS/2-DONE/<slug>/
Names: <slug>-<NN>-<role>.jpg/.webp, <same>-cut.png, <same>-wide.jpg (when made), plus <slug>.json sidecar.
Numbering is by position among ALL role-tagged photos (stable: a held-back photo never renumbers the others).
A project is only written when every role-tagged photo is 'done' (photos held by an override "skip" are left out of the numbering).
Otherwise its existing 2-DONE folder is left untouched and the reason is printed. Each project folder is built fresh in <slug>.tmp and swapped in,
so no stale file survives. Reads _work/meta/<project>.json. Role null (extra views) is left out.
Run from the 'ky box' folder:  python3 site/tools/finalize.py [project ...]"""
import os, sys, json, shutil, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')); W = os.path.join(ROOT, '_work'); DONE = os.path.join(ROOT, 'PHOTOS', '2-DONE')
ORDER = ['hero', 'front', 'back', 'side', 'open', 'insert', 'finish', 'set']; only = sys.argv[1:]
try: rep = json.load(open(os.path.join(W, 'processed', 'report.json')))
except (OSError, ValueError) as e: print('STOP: report.json missing or unreadable (%s). Run run_batch.py first.' % e); sys.exit(1)
NOMETA = sorted(d for d in os.listdir(os.path.join(ROOT, 'PHOTOS', '1-ORIGINALS')) if os.path.isdir(os.path.join(ROOT, 'PHOTOS', '1-ORIGINALS', d)) and d not in ('processed', 'ready') and not d.startswith(('_', '.')) and not os.path.exists(os.path.join(W, 'meta', d+'.json')))
if NOMETA: print('NO META YET (Claude must classify these before they can be finalized):', NOMETA)
os.makedirs(DONE, exist_ok=True); blocked = []
for mf in sorted(os.listdir(os.path.join(W, 'meta'))):
    if not mf.endswith('.json'): continue
    m = json.load(open(os.path.join(W, 'meta', mf))); slug = m['slug']
    if only and slug not in only: continue
    tagged = []
    for p in m['photos']:
        if not p.get('role'): continue
        if p['role'] not in ORDER: print('WARNING: unknown role %r on %s/%s, photo left out (known roles: %s)' % (p['role'], slug, p['file'], ', '.join(ORDER))); continue
        if (rep.get(f"{slug}/{p['file']}") or {}).get('status') == 'HOLD': continue
        tagged.append(p)
    tagged.sort(key=lambda p: (ORDER.index(p['role']), p['file']))
    bad = [(f"{slug}/{p['file']}", (rep.get(f"{slug}/{p['file']}") or {}).get('status', 'not processed')) for p in tagged if (rep.get(f"{slug}/{p['file']}") or {}).get('status') != 'done']
    if not tagged: print(slug, 'no role-tagged photos, nothing written'); continue
    if bad:
        blocked.append(slug); print('NOT WRITTEN (existing 2-DONE folder left alone):', slug, '->', '; '.join('%s is %s' % b for b in bad)); continue
    tmp = os.path.join(DONE, slug+'.tmp')
    if os.path.exists(tmp): shutil.rmtree(tmp, ignore_errors=True)
    if os.path.exists(tmp): os.rename(tmp, os.path.join(ROOT, 'PHOTOS', '_replaced', slug+'.tmp-'+str(int(time.time())))) if os.path.isdir(os.path.join(ROOT, 'PHOTOS', '_replaced')) else None
    os.makedirs(tmp); photos = []
    for n, ph in enumerate(tagged, 1):
        name = f"{slug}-{n:02d}-{ph['role']}"; src = os.path.join(W, 'processed', slug, os.path.splitext(ph['file'])[0])
        for ext in ('.jpg', '.webp', '-cut.png', '-wide.jpg'):
            if os.path.exists(src+ext): shutil.copyfile(src+ext, os.path.join(tmp, name+ext))
        photos.append({'file': name+'.jpg', 'role': ph['role'], 'alt': ph.get('alt', '')})
    side = {k: m.get(k) for k in ('slug', 'title', 'box_style', 'industry', 'finishes', 'brand_ok')}; side['photos'] = photos
    json.dump(side, open(os.path.join(tmp, slug+'.json'), 'w'), indent=1)
    out = os.path.join(DONE, slug)
    if os.path.exists(out):                       # swap: delete the old folder; where deleting is blocked, move it out of 2-DONE instead
        shutil.rmtree(out, ignore_errors=True)
        if os.path.exists(out):
            rd = os.path.join(ROOT, 'PHOTOS', '_replaced'); os.makedirs(rd, exist_ok=True); os.rename(out, os.path.join(rd, slug+'-'+str(int(time.time()))))
    os.rename(tmp, out); print(slug, len(photos), 'photos')
if blocked: print('PROJECTS NOT WRITTEN (%d):' % len(blocked), blocked)

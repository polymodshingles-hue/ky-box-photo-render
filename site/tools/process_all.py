#!/usr/bin/env python3
"""ONE COMMAND for the whole pipeline. Run from the 'ky box' folder:  python site/tools/process_all.py [project-folder ...]
Safe to run again at any time: a photo is redone only when the engine, its AI mask or its overrides changed.
Steps: mask check -> run_batch -> make_review -> finalize. Exit code 1 if any photo is CHECK/ERROR or a mask is missing (run_batch exits 3 for CHECK/ERROR; any other failure stops the run)."""
import subprocess, sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..', '..')); args = sys.argv[1:]
# --- every role-tagged photo needs an AI mask (made by make_masks.py on Claude's side); stop before processing if any is missing
ovp = os.path.join(HERE, 'overrides.json'); OV = json.load(open(ovp, encoding='utf-8')) if os.path.exists(ovp) else {}; miss = []
MD = os.path.join(ROOT, '_work', 'meta')
for mf in sorted(os.listdir(MD)):
    if not mf.endswith('.json'): continue
    m = json.load(open(os.path.join(MD, mf), encoding='utf-8')); slug = m['slug']
    if args and slug not in args: continue
    for ph in m['photos']:
        if not ph.get('role'): continue
        o = OV.get(ph['file'], {})
        if o.get('skip') or o.get('method') or o.get('rect'): continue
        mp = os.path.join(ROOT, '_work', 'masks', slug, os.path.splitext(ph['file'])[0] + '.png')
        if not os.path.exists(mp) or os.path.getsize(mp) < 100: miss.append(slug + '/' + ph['file'] + ' (no mask)')
        else:
            _src = os.path.join(ROOT, 'PHOTOS', '1-ORIGINALS', slug, ph['file'])
            if os.path.exists(_src) and os.stat(mp).st_mtime_ns < os.stat(_src).st_mtime_ns: miss.append(slug + '/' + ph['file'] + ' (mask older than the photo: remake it)')
if miss:
    print('STOP: %d photo(s) have no AI mask. Claude must run make_masks.py first. Nothing was processed.' % len(miss))
    for k in miss: print('  no mask:', k)
    sys.exit(1)
rc_batch = 0
for step, extra in (('run_batch.py', args), ('make_review.py', []), ('finalize.py', args)):
    print('=== ' + step, flush=True)
    rc = subprocess.call([sys.executable, os.path.join(HERE, step)] + extra, cwd=ROOT)
    if step == 'run_batch.py' and rc == 3: rc_batch = 1; continue      # CHECK/ERROR photos are held back; keep going so the good ones are finalized
    if step == 'finalize.py' and rc == 1: rc_batch = 1; continue      # some projects held back (CHECK photos); the rest were written
    if rc: print('STEP FAILED:', step, 'exit', rc); sys.exit(rc)
print('=== ALL STEPS DONE. Final files: PHOTOS\\2-DONE\\<slug>\\. Review sheets: _work\\processed\\review_*.jpg')
if rc_batch:
    print('BUT some photos are CHECK or ERROR (listed under run_batch above). Send that list to Claude.'); sys.exit(1)

#!/usr/bin/env python3
"""Batch runner for the workhorse. Processes every photo in PHOTOS/1-ORIGINALS/<project>/ with post_edit.py into
_work/processed/<project>/<file-stem>.jpg+.webp and writes _work/processed/report.json.
Resumes safely: a photo is redone when the engine version, its mask file, its overrides or its wide flag changed. Exits 1 when any photo is CHECK or ERROR (names printed last). Photos marked "skip" in overrides.json are logged, not processed.
Run from the 'ky box' folder:  python3 site/tools/run_batch.py [project-folder-name ...]"""
import os, sys, json, glob, time, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import post_edit as P
ROOT = os.path.abspath(os.path.join(HERE, '..', '..')); INBOX = os.path.join(ROOT, 'PHOTOS', '1-ORIGINALS'); OUT = os.path.join(ROOT, '_work', 'processed')
os.makedirs(OUT, exist_ok=True); rp = os.path.join(OUT, os.environ.get('REPORT_NAME', 'report.json'))
def save_report():                      # atomic: a killed run can never leave a half-written report.json
    tmp = rp + '.tmp'
    with open(tmp, 'w') as f: json.dump(report, f, indent=1)
    os.replace(tmp, rp)
try: report = json.load(open(rp)) if os.path.exists(rp) else {}
except ValueError:
    os.replace(rp, rp + '.corrupt'); report = {}; print('report.json was corrupt: moved aside as report.json.corrupt, starting fresh')
only = sys.argv[1:]
def meta_for(d):
    mp = os.path.join(ROOT, '_work', 'meta', d + '.json')
    return {x['file']: x for x in json.load(open(mp))['photos']} if os.path.exists(mp) else {}
SKIPDIRS = {'processed', 'ready', 'blue-test'}
_dirs = sorted(x for x in os.listdir(INBOX) if os.path.isdir(os.path.join(INBOX, x)) and x not in SKIPDIRS and not x.startswith(('_', '.')))
_missing = [o for o in only if o not in _dirs]
if _missing: print('ERROR: project folder not found:', _missing); sys.exit(1)
for d in _dirs:
    if only and d not in only: continue
    os.makedirs(os.path.join(OUT, d), exist_ok=True); MT = meta_for(d)
    _all = sorted(glob.glob(os.path.join(INBOX, d, '*')))
    for f in _all:
        if os.path.isfile(f) and f.lower().endswith(('.jpeg', '.png', '.heic', '.heif', '.dng', '.tif', '.tiff', '.webp')):
            k2 = f'{d}/{os.path.basename(f)}'; report[k2] = {'status': 'ERROR', 'error': 'unsupported file type (only .jpg is read)'}; print('ERROR', k2, 'unsupported file type')
    for f in [x for x in _all if x.lower().endswith('.jpg')]:
        name = os.path.basename(f); stem = os.path.splitext(name)[0]; key = f'{d}/{name}'; base = os.path.join(OUT, d, stem)
        ov = P.overrides(name); mp_ = P.mask_path(f); mt_ = os.path.getmtime(mp_) if os.path.exists(mp_) else None; ovs = json.dumps(ov, sort_keys=True)
        wide_ = bool(MT.get(name) and MT.get(name).get('wide')); old = report.get(key, {})
        if old.get('status') in ('done', 'CHECK') and os.path.exists(base + '.jpg') and old.get('engine') == P.ENGINE and old.get('mask_mtime') == mt_ and old.get('ov') == ovs and old.get('wide') == wide_: continue
        if ov.get('skip'): report[key] = {'status': 'HOLD', 'note': ov.get('note', '')}; print('HOLD', key); continue
        mt = MT.get(name)
        if MT and (mt is None or not mt.get('role')): report[key] = {'status': 'EXTRA', 'note': 'extra view, not used'}; print('extra', key); continue
        t = time.time()
        try: r = P.run(f, base, wide=bool(mt and mt.get('wide'))); r['status'] = 'done' if r.get('qc_ok') else 'CHECK'; r['mask_mtime'] = mt_; r['ov'] = ovs; r['secs'] = round(time.time()-t, 1); report[key] = r; print(r['status'], key, r['cutout'], r['qc'], r['secs'], 's')
        except Exception as e: report[key] = {'status': 'ERROR', 'error': str(e)}; print('ERROR', key, e); traceback.print_exc()
        save_report()
save_report()
print('finished:', sum(1 for v in report.values() if v.get('status') == 'done'), 'done,', sum(1 for v in report.values() if v.get('status') == 'HOLD'), 'hold,', sum(1 for v in report.values() if v.get('status') == 'ERROR'), 'errors')
bad = sorted(k for k, v in report.items() if v.get('status') in ('CHECK', 'ERROR') and (not only or k.split('/')[0] in only))
print('FAILED PHOTOS (%d) - CHECK = failed the quality test, ERROR = crashed. Needs Claude:' % len(bad))
for k in bad: print('  ', report[k]['status'], k, '-', report[k].get('qc') or report[k].get('error', ''))
sys.exit(1 if bad else 0)

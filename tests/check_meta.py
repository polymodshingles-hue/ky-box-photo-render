"""PR check: every _work/meta/*.json parses and uses the allowed vocabulary; overrides parse; each photo role is known."""
import json, glob, sys
ROLES = {'hero', 'front', 'back', 'side', 'open', 'insert', 'finish', 'set'}
STYLES = {'two-piece', 'neck', 'book-style', 'clamshell', 'slipcase-drawer', 'magnetic'}
INDUSTRIES = {'chocolates', 'wine-spirits', 'cannabis', 'pharmaceutical', 'health-beauty', 'gaming-entertainment', 'religious-publishing', 'retail-gift', 'automotive', 'other'}
bad = []
for f in sorted(glob.glob('_work/meta/*.json')):
    m = json.load(open(f))
    for k in ('slug', 'title', 'box_style', 'industry', 'photos'):
        if k not in m: bad.append(f'{f}: missing {k}')
    if m.get('box_style') not in STYLES: bad.append(f"{f}: box_style {m.get('box_style')!r}")
    if m.get('industry') not in INDUSTRIES: bad.append(f"{f}: industry {m.get('industry')!r}")
    for p in m.get('photos', []):
        if p.get('role') and p['role'] not in ROLES: bad.append(f"{f}: role {p['role']!r} on {p.get('file')}")
for f in glob.glob('site/tools/overrides*.json'): json.load(open(f))
print('\n'.join(bad) or 'meta ok'); sys.exit(1 if bad else 0)

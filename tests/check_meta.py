"""PR check: every _work/meta/*.json parses and uses the allowed vocabulary; slugs match file names; photo names are safe Windows .jpg
names with no case-insensitive duplicates; 'wide' is a real boolean; overrides parse."""
import glob, json, re, sys
from pathlib import Path
ROLES = {'hero', 'front', 'back', 'side', 'open', 'insert', 'finish', 'set'}
STYLES = {'two-piece', 'neck', 'book-style', 'clamshell', 'slipcase-drawer', 'magnetic'}
INDUSTRIES = {'chocolates', 'wine-spirits', 'cannabis', 'pharmaceutical', 'health-beauty', 'gaming-entertainment', 'religious-publishing', 'retail-gift', 'automotive', 'other'}
RESERVED = {'con', 'prn', 'aux', 'nul'} | {f'com{i}' for i in range(1, 10)} | {f'lpt{i}' for i in range(1, 10)}
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'site/tools'))
import pipeline
bad = []
files = sorted(glob.glob('_work/meta/*.json'))
if not files: bad.append('_work/meta: no project JSON files')
for f in files:
    m = pipeline.manifest(Path(f).stem)
    for k in ('slug', 'title', 'box_style', 'industry', 'photos'):
        if k not in m: bad.append(f'{f}: missing {k}')
    slug = m.get('slug')
    if not isinstance(slug, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug) or slug != Path(f).stem:
        bad.append(f'{f}: invalid slug or slug differs from the file name: {slug!r}')
    if m.get('box_style') not in STYLES: bad.append(f"{f}: box_style {m.get('box_style')!r}")
    if m.get('industry') not in INDUSTRIES: bad.append(f"{f}: industry {m.get('industry')!r}")
    photos = m.get('photos')
    if not isinstance(photos, list): bad.append(f'{f}: photos must be a list'); continue
    seen = set()
    for p in photos:
        if not isinstance(p, dict): bad.append(f'{f}: photo entry must be an object'); continue
        name = p.get('file')
        if not isinstance(name, str) or not re.fullmatch(r'[^<>:"/\\|?*\x00-\x1f]+\.jpg', name, re.I) or name.rsplit('.', 1)[0].lower() in RESERVED:
            bad.append(f'{f}: invalid .jpg file name {name!r}')
        else:
            stem = name.rsplit('.', 1)[0].casefold()
            if stem in seen: bad.append(f'{f}: duplicate output name (Windows ignores case) {name!r}')
            seen.add(stem)
        if p.get('role') is not None and p['role'] not in ROLES: bad.append(f"{f}: role {p['role']!r} on {name!r}")
        if 'wide' in p and not isinstance(p['wide'], bool): bad.append(f'{f}: wide must be true/false on {name!r}')
for f in glob.glob('site/tools/overrides*.json'):
    t = Path(f).read_text(encoding='utf-8').strip()
    for key, opts in json.loads(t).items():
        project, name = key.split('/')
        pipeline.slug(project)
        if Path(name).name != name or not isinstance(opts, dict):
            bad.append(f'Invalid override {key}')
        if 'focus_rect' in opts and 'focus_min' not in opts:
            bad.append(f'Missing focus_min for {key}')
print('\n'.join(bad) or 'meta ok'); sys.exit(1 if bad else 0)

"""Render selected local projects and persist per-photo provenance and status."""
import json
import uuid
import sys
import time
from pathlib import Path

import cv2
from PIL import Image
import pipeline as F
import post_edit as engine


def signature(source, options):
    mask = Path(engine.mask_path(source))
    source_hash = F.digest(source)
    mask_hash = None
    if not options.get('rect') and not options.get('method'):
        if not mask.is_file():
            raise ValueError('Missing mask. Run make_masks.py for this project.')
        with Image.open(mask) as image:
            if image.info.get('source_sha256') != source_hash:
                raise ValueError('Mask does not identify this original. Regenerate it with make_masks.py.')
        mask_hash = F.digest(mask)
    return dict(source=source_hash, mask=mask_hash, options=options, engine=engine.ENGINE)


def run(selected):
    cv2.setNumThreads(2)
    folders = F.projects(selected)
    try:
        report = F.read_json(F.REPORT, {})
        if not isinstance(report, dict) or any(not isinstance(v, dict) for v in report.values()):
            raise ValueError('Invalid report structure')
    except (json.JSONDecodeError, ValueError):
        backup = F.REPORT.with_name(f'report.{uuid.uuid4().hex}.corrupt')
        F.checked(F.REPORT).rename(backup)
        print('Rebuilding damaged report. Original saved at', backup)
        report = {}
    pending = set()
    bad = not folders
    if not folders:
        print("PENDING: no filed projects in PHOTOS/1-ORIGINALS")
    for project in folders:
        directory = F.ORIGINALS / project
        try:
            meta = F.manifest(project) if (F.META / (project + '.json')).exists() else {}
        except (ValueError, KeyError, TypeError) as exc:
            print('ERROR project metadata:', project, exc)
            bad = True
            continue
        photos = {p['file'].casefold(): p for p in meta.get('photos', [])}
        files = sorted(p for p in directory.iterdir() if p.is_file())
        seen = set()
        for source in files:
            entry = photos.get(source.name.casefold())
            name = entry['file'] if entry else source.name
            key = f'{project}/{name}'
            seen.add(key)
            options = F.options(project, name, meta.get('render_defaults'))
            old = report.get(key, {})
            if entry is None:
                row = dict(status='PENDING', note='Unclassified source')
                pending.add(str(source.relative_to(F.ROOT)))
            elif not entry.get('role'):
                row = dict(status='EXTRA', note='Explicitly excluded in metadata')
            elif options.get('skip'):
                row = dict(status='HOLD', note=options.get('note', ''))
            else:
                try:
                    sig = signature(source, options)
                    base = F.checked(F.PROCESSED / project / Path(name).stem)
                    base.parent.mkdir(parents=True, exist_ok=True)
                    paths = {ext: F.checked(str(base) + ext) for ext in F.VARIANTS}
                    if (old.get('signature') == sig and old.get('status') in ('done', 'CHECK')
                            and all(p.is_file() and F.digest(p) == old.get('hashes', {}).get(ext)
                                    for ext, p in paths.items())):
                        row = old
                    else:
                        report[key] = dict(status='PROCESSING')
                        F.atomic_json(F.REPORT, report)
                        start = time.monotonic()
                        row = engine.run(source, base, options=options)
                        if signature(source, options) != sig:
                            raise ValueError('Source or mask changed during render. Retry.')
                        row.update(status='done' if row['qc_ok'] else 'CHECK', signature=sig,
                                   hashes={ext: F.digest(p) for ext, p in paths.items()},
                                   secs=round(time.monotonic() - start, 2))
                except Exception as exc:
                    row = dict(status='ERROR', error=str(exc))
            report[key] = row
            print(row['status'], key, row.get('error') or row.get('qc') or row.get('note', ''), row.get('warn', ''))
            bad |= row['status'] in ('ERROR', 'CHECK', 'PENDING')
            if row != old:
                F.atomic_json(F.REPORT, report)
        for ph in photos.values():
            key = f"{project}/{ph['file']}"
            if ph.get('role') and key not in seen:
                seen.add(key)
                report[key] = dict(status='ERROR', error='Listed original is missing')
                print('ERROR', key, 'listed original is missing')
                bad = True
        for key in list(report):
            if key.startswith(project + '/') and key not in seen:
                del report[key]
        if not meta:
            print('PENDING missing project manifest:', project)
            bad = True
    F.atomic_json(F.REPORT, report)
    drop = F.ROOT / 'PHOTOS/0-DROP'
    pending.update(str(p.relative_to(F.ROOT)) for p in drop.rglob('*') if p.is_file())
    for folder in F.projects([]):
        pending.update(str(p.relative_to(F.ROOT)) for p in (F.ORIGINALS / folder).iterdir()
                       if p.is_file() and p.suffix.lower() in F.VIDEOS)
    pending.update(str(Path('PHOTOS/1-ORIGINALS') / key) for key, row in report.items()
                   if row['status'] == 'PENDING' and (F.ORIGINALS / key).is_file())
    F.atomic_json(F.WORK / 'pending.json', sorted(pending))
    if selected:     # a project run only fails on its own intake; other items stay listed in pending.json
        mine = tuple(str(Path('PHOTOS/1-ORIGINALS') / project) for project in folders)
        blocking = {item for item in pending if Path(item).as_posix().startswith(tuple(m.replace('\\', '/') + '/' for m in mine))}
    else:
        blocking = pending
    if pending:
        print('PENDING intake: see _work/pending.json' + ('' if blocking or not selected else ' (none for the selected projects)'))
    return 3 if bad or blocking else 0


if __name__ == '__main__':
    with F.writer():
        sys.exit(run(sys.argv[1:]))

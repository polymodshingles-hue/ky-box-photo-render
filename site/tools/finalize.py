"""Validate and promote complete local deliveries. Exit 3 for held projects."""
import shutil
import sys
from pathlib import Path
from PIL import Image

import pipeline as F
from run_batch import signature


def copy_checked(source, destination, suffix, expected):
    shutil.copyfile(source, destination)
    if F.digest(destination) != expected:
        raise ValueError(f'Changed render: {source.name}')
    fmt, size = F.VARIANTS[suffix]
    with Image.open(destination) as im:
        if im.format != fmt or im.size != size or (suffix == '-cut.png' and 'A' not in im.getbands()):
            raise ValueError(f'Invalid delivery variant: {source.name}')
        im.load()


def finalize(project, report):
    out = F.checked(F.DONE / project)
    F.recover(out)
    meta = F.manifest(project)
    directory = F.ORIGINALS / project
    listed = {p['file'].casefold() for p in meta['photos']}
    unknown = [p.name for p in directory.iterdir() if p.is_file() and p.name.casefold() not in listed]
    if unknown:
        raise ValueError('Unclassified sources: ' + ', '.join(sorted(unknown)))
    tagged = sorted((p for p in meta['photos'] if p.get('role')),
                    key=lambda p: (F.ROLES.index(p['role']), p['file']))
    copies = {}
    photos = []
    for n, photo in enumerate(tagged, 1):
        filename = photo['file']
        key = f'{project}/{filename}'
        options = F.options(project, filename, meta.get('render_defaults'))
        if options.get('skip'):
            print('HOLD', key)
            continue
        row = report.get(key, {})
        if row.get('status') != 'done':
            raise ValueError(f"{key}: {row.get('status', 'not processed')}")
        if row.get('signature') != signature(directory / filename, options):
            raise ValueError(f'{key}: original, mask or settings changed. Rerun batch.')
        name = f"{project}-{n:02d}-{photo['role']}"
        for ext in F.VARIANTS:
            src = F.checked(F.PROCESSED / project / (Path(filename).stem + ext))
            expected = row.get('hashes', {}).get(ext)
            if not expected or F.digest(src) != expected:
                raise ValueError(f'Changed or unverified scratch file: {src.name}')
            copies[name + ext] = src, ext, expected
        photos.append(dict(file=name + '.jpg', source_file=filename, role=photo['role'], alt=photo.get('alt', '')))
    if not photos:
        raise ValueError('No deliverable photos. Any previous final is from an earlier run.')
    side = {k: meta.get(k) for k in ('slug', 'title', 'box_style', 'industry', 'finishes', 'brand_ok', 'notes')}
    side['photos'] = photos
    side_name = project + '.json'
    if out.exists() and {p.name for p in out.iterdir()} == set(copies) | {side_name}:
        try:
            if (F.read_json(out / side_name) == side and
                    all(F.digest(F.checked(out / name)) == info[2] for name, info in copies.items())):
                print('unchanged', project)
                return
        except (OSError, ValueError):
            pass
    stage = F.new_stage(project)
    try:
        for dest, (src, ext, expected) in copies.items():
            copy_checked(src, stage / dest, ext, expected)
        F.atomic_json(stage / side_name, side)
        F.promote(stage, out)
    finally:
        if stage.exists():
            shutil.rmtree(F.checked(stage))
    print('finalized', project, len(photos), 'photos')


def run(selected):
    report = F.read_json(F.REPORT)
    F.checked(F.DONE).mkdir(parents=True, exist_ok=True)
    blocked = False
    for project in F.projects(selected):
        try:
            finalize(project, report)
        except (ValueError, KeyError, TypeError, FileNotFoundError) as exc:
            print('INCOMPLETE', project, exc)
            blocked = True
    return 3 if blocked else 0


if __name__ == '__main__':
    with F.writer():
        sys.exit(run(sys.argv[1:]))

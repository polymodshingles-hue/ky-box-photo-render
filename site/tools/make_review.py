"""Create scoped white-master and dark-background cutout contact sheets."""
import sys
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
import pipeline as F


def run(selected):
    projects = F.projects(selected)
    report = F.read_json(F.REPORT, {})
    items = [(k, v) for k, v in sorted(report.items())
             if k.split('/')[0] in projects and v.get('status') in ('done', 'CHECK')]
    scope = hashlib.sha256('\n'.join(projects).encode()).hexdigest()[:12] if selected else 'all'
    folder = F.checked(F.PROCESSED / 'reviews' / scope)
    folder.mkdir(parents=True, exist_ok=True)
    state = [[key, row['status'], row['qc'], row.get('hashes', {})] for key, row in items]
    stamp = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    marker = folder / 'sheets.json'
    expected = {folder / f'review_{kind}_{page + 1}.jpg' for kind in ('white', 'cut')
                for page in range((len(items) + 14) // 15)}
    if (F.read_json(marker, {}).get('stamp') == stamp and
            set(folder.glob('review_*.jpg')) == expected and all(p.stat().st_size for p in expected)):
        print('Review sheets unchanged:', folder)
        return
    active = set()
    for i in range(0, len(items), 15):
        group = items[i:i + 15]
        for cut in (False, True):
            sheet = Image.new('RGB', (1900, ((len(group) + 4) // 5) * 420), 'white')
            draw = ImageDraw.Draw(sheet)
            for index, (key, row) in enumerate(group):
                project, filename = key.split('/')
                suffix = '-cut.png' if cut else '.jpg'
                path = F.PROCESSED / project / (Path(filename).stem + suffix)
                x, y = (index % 5) * 380, (index // 5) * 420
                with Image.open(path) as im:
                    im.thumbnail((380, 380))
                    if cut:
                        bg = Image.new('RGBA', im.size, (40, 40, 40, 255))
                        bg.alpha_composite(im.convert('RGBA'))
                        sheet.paste(bg.convert('RGB'), (x, y))
                    else:
                        sheet.paste(im, (x, y))
                draw.text((x + 2, y + 381), key, fill='black')
                draw.text((x + 2, y + 397), (row['status'] + ' ' + row['qc'])[:62], fill='black')
            dest = folder / f"review_{'cut' if cut else 'white'}_{i // 15 + 1}.jpg"
            sheet.save(dest, quality=88)
            active.add(dest)
    for stale in folder.glob('review_*.jpg'):
        if stale not in active:
            F.checked(stale).unlink()
    F.atomic_json(marker, {'stamp': stamp})
    print('Review sheets:', folder)


if __name__ == '__main__':
    with F.writer():
        run(sys.argv[1:])

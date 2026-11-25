"""Generate source-bound masks on the machine with rembg installed."""
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageOps, PngImagePlugin
import pipeline as F

MODEL = 'isnet-general-use'
os.environ.setdefault('U2NET_HOME', os.path.expanduser('~/models'))


def usable(mask):
    hist = mask.convert('L').histogram()
    return .015 < sum(hist[128:]) / sum(hist) < .75


def run(selected):
    session = None
    for project in F.projects(selected):
        meta = F.manifest(project)
        for photo in meta['photos']:
            name = photo['file']
            options = F.options(project, name, meta.get('render_defaults'))
            if not photo.get('role') or any(options.get(k) for k in ('skip', 'method', 'rect')):
                continue
            source = F.ORIGINALS / project / name
            fingerprint = F.digest(source)
            target = F.checked(F.WORK / 'masks' / project / (Path(name).stem + '.png'))
            if target.is_file():
                try:
                    with Image.open(target) as mask:
                        if (mask.info.get('source_sha256') == fingerprint and mask.info.get('model') == MODEL
                                and usable(mask)):
                            continue
                except (OSError, SyntaxError):
                    pass
            if session is None:
                from rembg import new_session, remove
                session = new_session(MODEL)
            target.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source) as raw:
                image = ImageOps.exif_transpose(raw).convert('RGB')
            image.thumbnail((1600, 1600))
            result = remove(image, session=session, only_mask=True).convert('L')
            if not usable(result) or F.digest(source) != fingerprint:
                raise ValueError(f'Implausible mask area or original changed during inference: {source}')
            info = PngImagePlugin.PngInfo()
            info.add_text('source_sha256', fingerprint)
            info.add_text('model', MODEL)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as file:
                tmp = Path(file.name)
            try:
                result.save(tmp, 'PNG', pnginfo=info)
                os.replace(tmp, target)
            finally:
                tmp.unlink(missing_ok=True)
            print('mask', project, name)


if __name__ == '__main__':
    with F.writer():
        run(sys.argv[1:])

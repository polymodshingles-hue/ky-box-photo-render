"""Generate full-frame masks for spin frames: make_spin_masks.py FRAMES_DIR MASKS_DIR [PART N].
Frames are f_<number>.jpg. Masks keep the frame's aspect ratio (build_spin.py rejects anything else).
Resumable: existing masks are skipped. Run PART 0..N-1 of N in parallel (2 on the 2-core workhorse)."""
import os
import sys
from pathlib import Path

from PIL import Image, ImageOps

os.environ.setdefault('U2NET_HOME', os.path.expanduser('~/models'))


def run(frames, masks, part=0, parts=1, width=1080):
    from rembg import new_session, remove
    masks.mkdir(parents=True, exist_ok=True)
    session = new_session('isnet-general-use', providers=['CPUExecutionProvider'])
    for frame in sorted(frames.glob('f_*.jpg'))[part::parts]:
        target = masks / (frame.stem + '.png')
        if target.exists():
            continue
        with Image.open(frame) as image:
            image = ImageOps.exif_transpose(image).convert('RGB')
            image = image.resize((width, round(width * image.height / image.width)))
        mask = remove(image, session=session, only_mask=True)
        tmp = target.with_suffix('.tmp.png')
        mask.save(tmp)
        os.replace(tmp, target)


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) not in (2, 4):
        sys.exit(__doc__)
    run(Path(args[0]), Path(args[1]), *(int(v) for v in args[2:]))

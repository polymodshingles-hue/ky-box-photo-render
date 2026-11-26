"""Build a local spin from oriented full-frame images and corresponding masks."""
import sys
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

import pipeline as F
from post_edit import load, wb, SRGB_PROFILE

OUTPX = 1400


def frame_number(path):
    suffix = path.stem.removeprefix('f_')
    if not suffix.isascii() or not suffix.isdecimal():
        raise ValueError(f'Expected a numeric frame name: {path}')
    return int(suffix)


def mask_for(path, size):
    with Image.open(path) as image:
        mask = image.convert('L')
        if abs(mask.width / mask.height - size[0] / size[1]) > .02:
            raise ValueError(f'Mask aspect ratio differs from oriented frame: {path}')
        mask = mask.resize(size, Image.Resampling.BILINEAR)
    if not mask.point(lambda v: 255 if v > 127 else 0).getbbox():
        raise ValueError(f'Empty mask: {path}')
    return mask


def build(project, frames_dir, masks_dir):
    project = F.slug(project)
    frames = sorted(frames_dir.glob('f_*.jpg'), key=frame_number)
    if len(frames) < 8 or len({frame_number(p) for p in frames}) != len(frames):
        raise ValueError('Need at least eight uniquely numbered frames')
    masks = [masks_dir / (p.stem + '.png') for p in frames]
    target = F.checked(F.ROOT / 'PHOTOS/3-SPIN' / project)
    target.parent.mkdir(parents=True, exist_ok=True)
    F.recover(target)
    with Image.open(frames[0]) as image:
        size = ImageOps.exif_transpose(image).size
    cache = F.checked(F.WORK / 'spin' / (project + '.json'))
    signature = [[p.name, F.digest(p), F.digest(m)] for p, m in zip(frames, masks)]
    stats = F.read_json(cache, {})
    if stats.get('inputs') != signature or stats.get('version') != 1:
        boxes = []
        for frame, path in zip(frames, masks):
            with Image.open(frame) as im:
                if ImageOps.exif_transpose(im).size != size:
                    raise ValueError(f'Inconsistent oriented dimensions: {frame}')
            mask = mask_for(path, size)
            boxes.append(mask.point(lambda v: 255 if v > 127 else 0).getbbox())
        stats = dict(version=1, inputs=signature, boxes=boxes)
        F.atomic_json(cache, stats)
    boxes = np.array(stats['boxes'], dtype=int)
    left, top = boxes[:, :2].min(axis=0)
    right, bottom = boxes[:, 2:].max(axis=0)
    side = int(np.ceil(max(right - left, bottom - top) / .8))
    x = int((right + left - side) // 2)
    y = int((bottom + top - side) // 2)
    crop = (x, y, x + side, y + side)
    options = F.manifest(project).get('render_defaults', {}) if (F.META / (project + '.json')).exists() else {}
    stage = F.new_stage(project)
    try:
        (stage / 'frames').mkdir()
        for i, (frame, path) in enumerate(zip(frames, masks)):
            rgb = load(frame)
            if options.get('neutral_rgb') is not None:
                rgb = wb(rgb, options['neutral_rgb'])
            mask = mask_for(path, size)
            image = Image.fromarray(rgb).convert('RGBA')
            image.putalpha(mask)
            product = image.crop(crop).resize((OUTPX, OUTPX), Image.Resampling.LANCZOS)
            # Generate the floor shadow only from the bottom contact band.
            alpha = np.asarray(product.getchannel('A'))
            rows = np.where((alpha > 127).any(axis=1))[0]
            if not len(rows):
                raise ValueError(f'No visible product in {frame}')
            floor = int(rows[-1])
            shadow = np.zeros_like(alpha, dtype=np.float32)
            start = max(0, floor - 12)
            shadow[start+8:floor+9] = alpha[start:floor+1] / 255
            shadow = cv2.GaussianBlur(shadow, (0, 0), 12)
            base = Image.fromarray((255 * (1 - .35 * shadow)).astype(np.uint8)).convert('RGBA')
            base.alpha_composite(product)
            result = base.convert('RGB')
            result.save(stage / 'frames' / f'{i:03d}.webp', quality=88, method=4, icc_profile=SRGB_PROFILE)
            if i == 0:
                result.save(stage / 'poster.jpg', quality=92, subsampling=0, icc_profile=SRGB_PROFILE)
        (stage / 'index.html').write_text(viewer(len(frames)), encoding='utf-8')
        F.promote(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(F.checked(stage))
    print('Spin ready:', target)


def viewer(N):
    return """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>360 view</title>
<style>html,body{margin:0;background:#fff;font-family:system-ui,sans-serif}#w{max-width:900px;margin:0 auto;position:relative;touch-action:pan-y;user-select:none;cursor:grab}canvas{width:100%;display:block}
#h{position:absolute;bottom:10px;left:0;right:0;text-align:center;color:#888;font-size:14px;pointer-events:none}#b{position:absolute;top:8px;right:8px}button{border:1px solid #bbb;background:#fff;border-radius:6px;padding:6px 10px;cursor:pointer}</style></head>
<body><div id="w"><canvas id="c"></canvas><div id="b"><button id="p">Pause</button></div><div id="h">Drag to rotate</div></div>
<script>
const N=__N__,imgs=[],c=document.getElementById('c'),x=c.getContext('2d');let cur=0,loaded=0,auto=true,drag=false,sx=0,sf=0,vel=0,last=0,shown=-1;
const pad=n=>String(n).padStart(3,'0');
function show(i){i=((Math.round(i)%N)+N)%N;if(i===shown)return;const im=imgs[i];if(im&&im.complete&&im.naturalWidth){shown=i;if(c.width!==im.naturalWidth){c.width=im.naturalWidth;c.height=im.naturalHeight}x.drawImage(im,0,0)}}
for(let i=0;i<N;i++){const im=new Image();im.onload=()=>{loaded++;if(i===0||loaded===N)show(cur)};im.onerror=()=>{auto=false;document.getElementById('h').textContent='Frame unavailable'};im.src='frames/'+pad(i)+'.webp';imgs.push(im)}
function loop(t){if(auto&&!drag&&loaded>=N){cur+=(t-last)/1000*(N/10)}else if(!drag&&Math.abs(vel)>.02){cur+=vel;vel*=.94}last=t;show(cur);requestAnimationFrame(loop)}requestAnimationFrame(loop);
const w=document.getElementById('w');
w.addEventListener('pointerdown',e=>{if(e.target.closest('button'))return;drag=true;auto=false;sx=e.clientX;sf=cur;vel=0;document.getElementById('p').textContent='Play';w.setPointerCapture(e.pointerId)});
w.addEventListener('pointermove',e=>{if(!drag)return;const p=cur;cur=sf-(e.clientX-sx)/w.clientWidth*N*1.2;vel=cur-p});
w.addEventListener('pointerup',()=>{drag=false});w.addEventListener('pointercancel',()=>{drag=false;vel=0});
document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'){auto=false;cur-=1}if(e.key==='ArrowRight'){auto=false;cur+=1}});
document.getElementById('p').onclick=e=>{auto=!auto;e.target.textContent=auto?'Pause':'Play';vel=0};
</script></body></html>""".replace('__N__', str(N))


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) not in (1, 3):
        sys.exit("Usage: build_spin.py PROJECT [FRAMES_DIR MASKS_DIR]")
    with F.writer():
        build(args[0], Path(args[1]) if len(args) == 3 else Path.home() / "sp_full",
              Path(args[2]) if len(args) == 3 else Path.home() / "sp_mask")

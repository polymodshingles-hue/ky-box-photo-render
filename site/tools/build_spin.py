#!/usr/bin/env python3
"""360 spin builder (separate from the photo pipeline).  usage: build_spin.py <slug> [frames_dir masks_dir]
Reads full-size frames + AI masks (made on Claude's side), applies ONE crop and ONE grade to every frame (so nothing jumps or flickers),
composites on white with a fixed soft shadow, writes PHOTOS/3-SPIN/<slug>/frames/NNN.webp (+ poster.jpg) and index.html (drag/swipe viewer)."""
import os, sys, json, glob, numpy as np, cv2
from PIL import Image
HOME = os.path.expanduser('~'); ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
slug = sys.argv[1]; FD = sys.argv[2] if len(sys.argv) > 2 else HOME+'/sp_full'; MD = sys.argv[3] if len(sys.argv) > 3 else HOME+'/sp_mask'
CROP = (0, 900, 2160, 3500); OUTPX = 1400; OUT = os.path.join(ROOT, 'PHOTOS', '3-SPIN', slug); os.makedirs(OUT+'/frames', exist_ok=True)
fs = sorted(glob.glob(FD+'/f_*.jpg')); N = len(fs); print(N, 'frames')
if N < 8: sys.exit('ERROR: need at least 8 frames f_*.jpg in ' + FD)
def mask_for(f, size):
    k = os.path.splitext(os.path.basename(f))[0]
    try:
        with Image.open(os.path.join(MD, k + '.png')) as _mi: m = np.array(_mi.convert('L'))      # PIL: cv2.imread cannot open non-ASCII paths on Windows
    except (OSError, SyntaxError): sys.exit('ERROR: missing or unreadable mask for frame ' + k + ' in ' + MD)
    m = cv2.resize(m, size, interpolation=cv2.INTER_CUBIC); m = ((m > 127)*255).astype(np.uint8)
    n, lb, st, _ = cv2.connectedComponentsWithStats((m > 0).astype(np.uint8), 8)
    if n > 2: m = ((lb == 1+int(np.argmax(st[1:, 4])))*255).astype(np.uint8)
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE); fl = np.zeros_like(m); cv2.drawContours(fl, cs, -1, 255, cv2.FILLED)
    b = cv2.GaussianBlur(fl, (0, 0), 3); return ((b > 127)*255).astype(np.uint8)
# ---- pass 1: geometry + color statistics for the whole sequence
W0, H0 = CROP[2]-CROP[0], CROP[3]-CROP[1]; boxes = []; bg_med = []; box_L = []; foot = []
CACHE = f'{HOME}/sp_stats_{slug}.json'
def _sig():          # the stats cache is only valid for these exact frames, masks and crop
    return [list(CROP), N, [[os.path.basename(f), os.stat(f).st_size, os.stat(f).st_mtime_ns] for f in fs],
            [[q, os.stat(q).st_size, os.stat(q).st_mtime_ns] for q in sorted(glob.glob(MD + '/f_*.png'))]]
try: _cc = json.load(open(CACHE, encoding='utf-8')); _cached = _cc if _cc.get('sig') == _sig() else None
except (OSError, ValueError): _cached = None
for f in (fs if _cached is None else []):
    im = np.array(Image.open(f).convert('RGB').crop(CROP)); m = mask_for(f, (W0, H0)); ys, xs = np.where(m > 0); boxes.append((xs.min(), ys.min(), xs.max(), ys.max()))
    small = cv2.resize(im, None, fx=.25, fy=.25, interpolation=cv2.INTER_AREA); ms = cv2.resize(m, (small.shape[1], small.shape[0])) > 127
    bgm = ~cv2.dilate(ms.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool); bg_med.append(np.median(small[bgm].reshape(-1, 3), 0))
    L = cv2.cvtColor(small, cv2.COLOR_RGB2LAB)[..., 0][ms]; box_L.append(L)
    hh = ys.max()-ys.min(); rows = m[int(ys.max()-hh*.06):ys.max()+1] > 0; foot.append(float(rows.sum(1).mean()))
if _cached is not None:
    _c = _cached; boxes = _c['boxes']; bg_med = _c['bg_med']; foot = _c['foot']; allL = np.array(_c['allL'], np.float32)
else:
    allL = np.concatenate([b.ravel() for b in box_L]).astype(np.float32)[::7]; json.dump({'sig': _sig(), 'boxes': np.array(boxes).tolist(), 'bg_med': np.array(bg_med).tolist(), 'foot': foot, 'allL': allL.tolist()}, open(CACHE + '.%d.tmp' % os.getpid(), 'w', encoding='utf-8')); os.replace(CACHE + '.%d.tmp' % os.getpid(), CACHE)
boxes = np.array(boxes); axis_x = float(np.median((boxes[:, 0]+boxes[:, 2])/2)); base_y = float(np.median(boxes[:, 3])); top_y = float(boxes[:, 1].min())
height = base_y-top_y; side = int(max(height*1.28, (boxes[:, 2]-boxes[:, 0]).max()*1.45)); side = min(side, W0, H0); half = side//2      # a very wide box gets less margin instead of crashing
cx = axis_x; cy = top_y+height*.5+side*.02
x0, y0 = int(cx-half), int(cy-half); x0 = max(0, min(W0-side, x0)); y0 = max(0, min(H0-side, y0)); print('window', x0, y0, side, 'axis', round(axis_x), 'base', round(base_y))
_bg = np.median(bg_med, 0); gain = np.clip(_bg.mean()/_bg, .9, 1.12) if _bg.max()-_bg.min() <= 40 else np.ones(3); print('neutral gain', gain.round(3))     # one white balance for the whole spin (backdrop -> neutral)
medL = float(np.median(allL)); hiL = float(np.percentile(allL, 99.5))
tgt = min(150.0, medL+(150-medL)*.8) if medL < 150 else medL; g = np.log(max(tgt, 1)/255)/np.log(max(medL, 1)/255); g = float(np.clip(g, .6, 1.2)); print('box median L', round(medL), '-> gamma', round(g, 3), 'hi', round(hiL))
fw = float(np.median(boxes[:, 2]-boxes[:, 0])); sh_cx = axis_x-x0; sh_cy = base_y-y0
def smooth(v, k=9): v = np.asarray(v, float); return np.convolve(np.pad(v, k//2, mode='wrap'), np.full(k, 1.0/k), mode='valid')      # circular moving average, always len(v) values
bot_s = smooth(boxes[:, 3]); foot_s = smooth(foot)
def make_shadow(i):
    sh = np.zeros((side, side), np.float32); cv2.ellipse(sh, (int(axis_x-x0), int(bot_s[i]-y0-max(foot_s[i], fw*.55)*.07)), (int(foot_s[i]*.58), int(max(foot_s[i], fw*.55)*.085)), 0, 0, 360, 1.0, -1)
    return cv2.GaussianBlur(sh, (0, 0), fw*.035)*.30
# ---- pass 2: render
def grade(a, m):
    a = np.clip(a.astype(np.float32)*gain, 0, 255); lab = cv2.cvtColor(a.astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32); L = lab[..., 0]
    L = 255*(L/255)**g; L = np.clip(L+.12*(L-cv2.GaussianBlur(L, (0, 0), side/70.0)), 0, 255)       # one tone curve + light clarity
    x = np.clip(L/255, 0, 1); L = 255*np.clip(x+.9*x*(1-x)*(x-.5)*.5, 0, 1); lab[..., 0] = L
    lab[..., 1] = 128+(lab[..., 1]-128)*1.10; lab[..., 2] = 128+(lab[..., 2]-128)*1.10                 # a touch of color
    out = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB); bl = cv2.GaussianBlur(out, (0, 0), 1.6)
    return np.clip(out.astype(np.float32)+.45*(out.astype(np.float32)-bl), 0, 255)
_a, _b = [int(v) for v in os.environ.get('RANGE', f'0:{N}').split(':')]
for i, f in enumerate(fs):
    if not (_a <= i < _b): continue
    im = np.array(Image.open(f).convert('RGB').crop(CROP)); m = mask_for(f, (W0, H0))
    im = im[y0:y0+side, x0:x0+side]; m = m[y0:y0+side, x0:x0+side]
    m = cv2.erode(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))); soft = cv2.GaussianBlur(m.astype(np.float32)/255, (0, 0), 1.6)[..., None]
    g_ = grade(im, m); comp = g_*soft+(255*(1-make_shadow(i)[..., None]))*(1-soft)
    Image.fromarray(np.clip(comp, 0, 255).astype(np.uint8)).resize((OUTPX, OUTPX), Image.LANCZOS).save(f'{OUT}/frames/{i:03d}.webp', 'WEBP', quality=88, method=5)
    if i == 0: Image.fromarray(np.clip(comp, 0, 255).astype(np.uint8)).save(f'{OUT}/poster.jpg', 'JPEG', quality=92)
html = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>360 view</title>
<style>html,body{margin:0;background:#fff;font-family:system-ui,sans-serif}#w{max-width:900px;margin:0 auto;position:relative;touch-action:pan-y;user-select:none;cursor:grab}canvas{width:100%;display:block}
#h{position:absolute;bottom:10px;left:0;right:0;text-align:center;color:#888;font-size:14px;pointer-events:none}#b{position:absolute;top:8px;right:8px}button{border:1px solid #bbb;background:#fff;border-radius:6px;padding:6px 10px;cursor:pointer}</style></head>
<body><div id="w"><canvas id="c"></canvas><div id="b"><button id="p">Pause</button></div><div id="h">Drag to rotate</div></div>
<script>
const N=__N__,imgs=[],c=document.getElementById('c'),x=c.getContext('2d');let cur=0,loaded=0,auto=true,drag=false,sx=0,sf=0,vel=0,last=0,shown=-1;
const pad=n=>String(n).padStart(3,'0');
function show(i){i=((Math.round(i)%N)+N)%N;if(i===shown)return;const im=imgs[i];if(im&&im.complete&&im.naturalWidth){shown=i;if(c.width!==im.naturalWidth){c.width=im.naturalWidth;c.height=im.naturalHeight}x.drawImage(im,0,0)}}
for(let i=0;i<N;i++){const im=new Image();im.onload=()=>{loaded++;if(i===0||loaded===N)show(cur)};im.src='frames/'+pad(i)+'.webp';imgs.push(im)}
function loop(t){if(auto&&!drag&&loaded>=N){cur+=(t-last)/1000*(N/10)}else if(!drag&&Math.abs(vel)>.02){cur+=vel;vel*=.94}last=t;show(cur);requestAnimationFrame(loop)}requestAnimationFrame(loop);
const w=document.getElementById('w');
w.addEventListener('pointerdown',e=>{drag=true;auto=false;sx=e.clientX;sf=cur;vel=0;document.getElementById('p').textContent='Play';w.setPointerCapture(e.pointerId)});
w.addEventListener('pointermove',e=>{if(!drag)return;const p=cur;cur=sf-(e.clientX-sx)/w.clientWidth*N*1.2;vel=cur-p});
w.addEventListener('pointerup',()=>{drag=false});w.addEventListener('pointercancel',()=>{drag=false;vel=0});
document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'){auto=false;cur-=1}if(e.key==='ArrowRight'){auto=false;cur+=1}});
document.getElementById('p').onclick=e=>{auto=!auto;e.target.textContent=auto?'Pause':'Play';vel=0};
</script></body></html>""".replace('__N__', str(N))
open(OUT+'/index.html', 'w', encoding='utf-8').write(html); print('done ->', OUT)

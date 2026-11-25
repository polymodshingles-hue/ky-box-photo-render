#!/usr/bin/env python3
"""KY Box photo post-edit (v4). Studio look: white-balance, cutout, pure-white backdrop + contact shadow, even lighting,
color pop, dust/lint cleanup, tear/defect repair from overrides.json, consistent square canvas, 2000px jpg+webp.
Usage:
  python3 post_edit.py IN.jpg OUT_BASE            process one photo
  python3 post_edit.py --maskcheck DIR OUT.jpg    preview cutouts for every photo under DIR (contact sheet, fast)
overrides.json (same folder), keyed by file name:
  {"PXL_x.jpg": {"rect":[l,t,r,b], "repair":[[l,t,r,b],...], "clone":[[src_l,src_t,src_r,src_b,dst_l,dst_t],...], "note":"..."}}
  all numbers are fractions (0-1) of the FULL photo. rect = where the box is (forces the cutout). repair = inpaint those areas
  (tears, rips, scuffs). clone = copy a clean patch over a damaged spot (for printed art)."""
import sys, os, json, glob, numpy as np, cv2
from PIL import Image, ImageOps, ImageEnhance, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = 'v16'
def overrides(name):
    p = os.path.join(HERE, 'overrides.json')
    return json.load(open(p, encoding='utf-8')).get(name, {}) if os.path.exists(p) else {}

def mask_path(src):
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '_work', 'masks', os.path.basename(os.path.dirname(os.path.abspath(src))), os.path.splitext(os.path.basename(src))[0]+'.png')

def backdrop_sample(a, fg):
    """Backdrop color from a ring along the photo border, with the (widened) box mask excluded. Returns (rgb median or None, clean fraction of photo)."""
    _f = 8; a = a[::_f, ::_f]; fg = fg[::_f, ::_f]          # analysis at 1/8 scale: same colour within 1 level, ~100x faster
    h, w = a.shape[:2]; k = max(3, int(max(h, w)*.03))
    wide = cv2.dilate((fg > 127).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    ring = np.zeros((h, w), bool); bw = max(2, int(min(h, w)*.08)); ring[:bw] = True; ring[-bw:] = True; ring[:, :bw] = True; ring[:, -bw:] = True
    sel = ring & (wide == 0); frac = float(sel.mean())
    if frac < .02: return None, frac
    return np.median(a[sel].reshape(-1, 3).astype(float), 0), frac

def _chroma(a, m):
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32); A, B = lab[..., 1]-128, lab[..., 2]-128
    return float(np.sqrt(A**2+B**2)[m].mean()) if m.any() else 0.0

def art_protect(a, fg):
    """1 = plain paper (bounce cast may be removed), 0 = printed art (leave its colour alone). Art = pixels whose a*/b* differ from the smooth paper colour around them."""
    m = fg > 127; h, w = m.shape; k = 128.0/max(h, w); sz = (max(8, int(w*k)), max(8, int(h*k)))
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB); ms = cv2.resize(m.astype(np.uint8), sz, interpolation=cv2.INTER_NEAREST) > 0
    if ms.sum() < 20: return np.ones((h, w), np.float32)
    out = []
    for c in (1, 2):
        s = cv2.resize(lab[..., c], sz, interpolation=cv2.INTER_AREA); s[~ms] = int(np.median(s[ms]))
        out.append(cv2.resize(cv2.medianBlur(s, 41), (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32))
    d = np.sqrt((lab[..., 1].astype(np.float32)-out[0])**2+(lab[..., 2].astype(np.float32)-out[1])**2)
    return cv2.GaussianBlur(1-np.clip((d-5)/5.0, 0, 1), (0, 0), 1.5)

def _atomic(img, path, fmt, **kw):
    """Save to a temp name then rename, so a killed run never leaves a truncated deliverable."""
    tmp = path + '.tmp'
    img.save(tmp, fmt, **kw); os.replace(tmp, path)

def load(p):
    im = ImageOps.exif_transpose(Image.open(p)); icc = im.info.get('icc_profile')
    if icc:                                     # wide-gamut phone shots (Display P3) must be converted to sRGB, not just relabelled
        try:
            import io; from PIL import ImageCms
            im = ImageCms.profileToProfile(im.convert('RGB'), ImageCms.ImageCmsProfile(io.BytesIO(icc)), ImageCms.createProfile('sRGB'), outputMode='RGB')
        except Exception: pass
    return np.array(im.convert('RGB'))

def wb(a, med=None):
    """med = measured backdrop color (from the photo border, outside the box). None = old top-strip reading."""
    h, w, _ = a.shape
    if med is None:
        top = a[:int(h*.12), int(w*.25):int(w*.75)].reshape(-1, 3).astype(float)
        med = np.median(top, 0)
    med = np.maximum(np.asarray(med, float), 1)
    if med.max()-med.min() > 40:   # colored backdrop (blue/green): do not white-balance on it, that would tint the whole box
        return a
    if med.mean() < 215:   # gray backdrop: neutralize the color cast only; do not brighten (keeps pale boxes separable from the backdrop)
        g = np.clip(med.mean()/med, .8, 1.25)
    else:
        g = np.clip(243/med, .8, 1.45)
    return np.clip(a*g, 0, 255).astype(np.uint8)

# ---------- cutout ----------
def _grabcut_refine(s, fg0, iters=4):
    m = np.full(fg0.shape, cv2.GC_BGD, np.uint8)
    k = max(3, int(min(fg0.shape)*.012))
    dil = cv2.dilate(fg0, np.ones((k*3, k*3), np.uint8)); ero = cv2.erode(fg0, np.ones((k*2, k*2), np.uint8))
    m[dil > 0] = cv2.GC_PR_BGD; m[fg0 > 0] = cv2.GC_PR_FGD; m[ero > 0] = cv2.GC_FGD
    bg = np.zeros((1, 65)); fg = np.zeros((1, 65))
    cv2.grabCut(cv2.cvtColor(s, cv2.COLOR_RGB2BGR), m, None, bg, fg, iters, cv2.GC_INIT_WITH_MASK)
    return ((m == cv2.GC_FGD) | (m == cv2.GC_PR_FGD)).astype(np.uint8)

def _clean(fgm):
    fgm = (fgm > 0).astype(np.uint8)*255
    n, lab, st, _ = cv2.connectedComponentsWithStats(fgm)
    if n > 1: fgm = ((lab == 1+np.argmax(st[1:, 4]))*255).astype(np.uint8)
    fgm = cv2.morphologyEx(fgm, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    ff = fgm.copy(); hh, ww = ff.shape; mk = np.zeros((hh+2, ww+2), np.uint8); cv2.floodFill(ff, mk, (0, 0), 255)
    return fgm | cv2.bitwise_not(ff)

def mask_flood(s, cut=0, rect=None):
    """Backdrop = smooth (low-gradient) pixels connected to the frame edge; box = what's left, then edge-refined."""
    lab = cv2.cvtColor(cv2.GaussianBlur(s, (0, 0), 2), cv2.COLOR_RGB2LAB).astype(np.float32)
    gx = sum(cv2.Sobel(lab[..., i], cv2.CV_32F, 1, 0) for i in range(3)); gy = sum(cv2.Sobel(lab[..., i], cv2.CV_32F, 0, 1) for i in range(3))
    mag = np.sqrt(gx**2+gy**2)
    cand = (mag < 14).astype(np.uint8)
    n, lb, st, _ = cv2.connectedComponentsWithStats(cand)
    sh, sw = cand.shape; bgm = np.zeros_like(cand)
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a > 400 and (x == 0 or y == 0 or x+w >= sw or y+h >= sh): bgm[lb == i] = 1
    fg0 = 1-bgm
    if rect:
        rm = np.zeros_like(fg0); rm[int(rect[1]*sh):int(rect[3]*sh), int(rect[0]*sw):int(rect[2]*sw)] = 1; fg0 = fg0 & rm
    fg0 = cv2.morphologyEx(fg0, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n, lb, st, _ = cv2.connectedComponentsWithStats(fg0)
    if n < 2: return None
    if rect:
        keep = np.zeros_like(fg0); mx = st[1:, 4].max()
        for i in range(1, n):
            if st[i, 4] > .08*mx: keep[lb == i] = 1
        return _grabcut_refine(s, _clean(keep)//255)
    cen = lb[int(sh*.55), int(sw*.5)]
    if cen == 0:
        cen = 1+np.argmax(st[1:, 4])
    fg0 = (lb == cen).astype(np.uint8)
    if cut:   # sever thin/wide attachments (tent walls) that touch the box: erode, keep center piece(s), grow back inside the original
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*cut+1, 2*cut+1))
        core = cv2.erode(fg0, k); n2, l2, s2, _ = cv2.connectedComponentsWithStats(core)
        if n2 < 2: return None
        keep = np.zeros_like(core)
        c0 = l2[int(sh*.55), int(sw*.5)]
        big = [i for i in range(1, n2) if s2[i, 4] > .25*s2[1:, 4].max()]
        for i in (big if c0 == 0 else [c0]+[j for j in big if j != c0]): keep[l2 == i] = 1
        fg0 = cv2.dilate(keep, k) & fg0
    fg0 = _clean(fg0)//255
    return _grabcut_refine(s, fg0)

def mask_canny(s):
    sh, sw = s.shape[:2]
    g = cv2.GaussianBlur(cv2.cvtColor(s, cv2.COLOR_RGB2GRAY), (5, 5), 0)
    e = cv2.dilate(cv2.Canny(g, 12, 36), np.ones((5, 5), np.uint8))
    e[:, :int(sw*.06)] = 0; e[:, int(sw*.94):] = 0; e[:int(sh*.04)] = 0
    cs, _ = cv2.findContours(e, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE); best = None; ba = 0
    for c in cs:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw*ch > ba and x > sw*.04 and x+cw < sw*.96: ba = cw*ch; best = (x, y, cw, ch)
    if best is None: return None
    x, y, cw, ch = best
    fg0 = np.zeros((sh, sw), np.uint8); fg0[y:y+ch, x:x+cw] = 1
    return _grabcut_refine(s, fg0)

def mask_bgdist(s):
    """Gray/colored backdrop: fit a smooth backdrop surface from the frame border, box = pixels that differ from it."""
    sh, sw = s.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(s, (0, 0), 2), cv2.COLOR_RGB2LAB).astype(np.float32)
    yy, xx = np.mgrid[0:sh, 0:sw]; X = xx/sw; Y = yy/sh
    ring = np.zeros((sh, sw), bool); b = int(.06*min(sh, sw))
    ring[:b] = 1; ring[:, :b] = 1; ring[:, -b:] = 1; ring[-int(b*.6):] = 1
    A = np.stack([np.ones_like(X), X, Y, X*X, Y*Y, X*Y], -1)
    use = ring.copy(); dist = np.zeros((sh, sw), np.float32)
    for it in range(3):
        d2 = np.zeros((sh, sw), np.float32)
        for c in range(3):
            co, *_ = np.linalg.lstsq(A[use], lab[..., c][use], rcond=None)
            d2 += (lab[..., c]-A@co)**2
        dist = np.sqrt(d2); r = dist[ring]; thr = max(7.0, float(np.median(r)+4*r.std()))
        use = ring & (dist < thr)
    fg0 = (dist > thr).astype(np.uint8)
    fg0 = cv2.morphologyEx(fg0, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    n, lb, st, _ = cv2.connectedComponentsWithStats(fg0)
    if n < 2: return None
    keep = np.zeros_like(fg0); mx = st[1:, 4].max()
    for i in range(1, n):
        if st[i, 4] > .12*mx: keep[lb == i] = 1
    return _grabcut_refine(s, _clean(keep)//255)

def mask_edgefill(s):
    """Pale box on a gray backdrop: close the box outline from its edges, fill the inside, keep the big pieces."""
    sh, sw = s.shape[:2]
    g = cv2.GaussianBlur(cv2.cvtColor(s, cv2.COLOR_RGB2GRAY), (0, 0), 1.6)
    e = cv2.Canny(g, 6, 18)
    e[:, :int(sw*.03)] = 0; e[:, int(sw*.97):] = 0; e[:int(sh*.02)] = 0
    k = max(5, int(sw*.012)); e = cv2.morphologyEx(e, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k*2+1, k*2+1)))
    ff = e.copy(); mk = np.zeros((sh+2, sw+2), np.uint8); cv2.floodFill(ff, mk, (0, 0), 255)
    fill = (e | cv2.bitwise_not(ff)) > 0
    fill = cv2.morphologyEx(fill.astype(np.uint8), cv2.MORPH_OPEN, np.ones((k*2+1, k*2+1), np.uint8))
    n, lb, st, _ = cv2.connectedComponentsWithStats(fill)
    if n < 2: return None
    keep = np.zeros_like(fill); mx = st[1:, 4].max()
    for i in range(1, n):
        if st[i, 4] > .15*mx: keep[lb == i] = 1
    return _grabcut_refine(s, _clean(keep)//255)

def qc_mask(m):
    if m is None or m.sum() == 0: return False, 'empty'
    sh, sw = m.shape; ys, xs = np.where(m > 0)
    frac = m.sum()/(sh*sw)
    cs, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    c = max(cs, key=cv2.contourArea); sol = cv2.contourArea(c)/max(cv2.contourArea(cv2.convexHull(c)), 1)
    bw = (xs.max()-xs.min())/sw; bh = (ys.max()-ys.min())/sh
    why = []
    if not .03 < frac < .72: why.append(f'area {frac:.2f}')
    if xs.min() < sw*.01 or xs.max() > sw*.99 or ys.min() < sh*.01 or ys.max() > sh*.99: why.append('touches frame edge')
    if sol < .60: why.append(f'ragged {sol:.2f}')
    if bw > .9 or bh > .93: why.append('too big')
    return (not why), ', '.join(why) or 'ok'

def refine_hi(a, m, work=1800):
    """Snap the outline to the real edge at higher resolution (the analysis runs at 1000 px, which leaves stair-steps)."""
    h, w = a.shape[:2]; k = work/max(h, w)
    img = cv2.resize(a, (int(w*k), int(h*k)), interpolation=cv2.INTER_AREA)
    mm = (cv2.resize(m, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LINEAR) > 127).astype(np.uint8)
    r = max(3, int(work*.004)); gm = np.full(mm.shape, cv2.GC_BGD, np.uint8)
    gm[cv2.dilate(mm, np.ones((r*2+1, r*2+1), np.uint8)) > 0] = cv2.GC_PR_BGD; gm[mm > 0] = cv2.GC_PR_FGD
    gm[cv2.erode(mm, np.ones((r*2+1, r*2+1), np.uint8)) > 0] = cv2.GC_FGD
    bg = np.zeros((1, 65)); fg = np.zeros((1, 65))
    try: cv2.grabCut(cv2.cvtColor(img, cv2.COLOR_RGB2BGR), gm, None, bg, fg, 3, cv2.GC_INIT_WITH_MASK)
    except Exception: return m
    out = ((gm == cv2.GC_FGD) | (gm == cv2.GC_PR_FGD)).astype(np.uint8)*255
    out = cv2.medianBlur(out, 5)
    if out.sum() < .6*mm.sum()*255 or out.sum() > 1.4*mm.sum()*255: return m      # refinement drifted: keep the safe mask
    return cv2.resize(out, (w, h), interpolation=cv2.INTER_LINEAR)

def mask_box(a, rect=None, method_force=None, cut=None):
    h, w, _ = a.shape; sc = 1000/max(h, w); s = cv2.resize(a, (int(w*sc), int(h*sc)), interpolation=cv2.INTER_AREA)
    sh, sw = s.shape[:2]; tried = []
    if method_force in ('flood', 'flood-cut', 'canny', 'bgdist', 'edgefill'):
        fn = {'flood': lambda z: mask_flood(z, 0), 'flood-cut': lambda z: mask_flood(z, int(z.shape[1]*(cut or .04))), 'canny': mask_canny, 'bgdist': mask_bgdist, 'edgefill': mask_edgefill}[method_force]
        m = fn(s); ok, why = qc_mask(m) if m is not None else (False, 'empty'); method = 'forced-'+method_force
        if m is None: m = np.zeros((sh, sw), np.uint8)
    elif rect:
        rl = rect if isinstance(rect[0], (list, tuple)) else [rect]; m = None
        for rr in rl:
            mi = mask_flood(s, 0, rr)
            if mi is not None: m = mi if m is None else (m | mi)
        method = 'rect-flood'
        ok, why = qc_mask(m) if m is not None else (False, 'empty')
        if m is None: m = np.zeros((sh, sw), np.uint8)
    else:
        for name, fn in (('flood', mask_flood), ('flood-cut', lambda z: mask_flood(z, int(z.shape[1]*.04))), ('bgdist', mask_bgdist), ('edgefill', mask_edgefill), ('canny', mask_canny)):
            m = fn(s); ok, why = qc_mask(m); tried.append(f'{name}:{why}')
            if ok and name == 'canny' and m.sum()/max(1, (np.ptp(np.where(m > 0)[0])+1)*(np.ptp(np.where(m > 0)[1])+1)) > .93: ok, why = False, 'boxy canny'
            if ok:
                method = name
                if name in ('flood', 'flood-cut', 'bgdist') and np.median(a[:int(h*.12), int(w*.25):int(w*.75)]) < 215:   # gray backdrop: add what the outline method sees too (e.g. second piece of a two-piece box)
                    m2 = mask_edgefill(s)
                    if m2 is not None and qc_mask(m2)[0]:
                        mu = (m > 0) | (m2 > 0); mu = _clean(mu.astype(np.uint8)*255)
                        if qc_mask(mu > 0)[0]: m = (mu > 0).astype(np.uint8); method = name+'+edge'
                break
        else:
            method = 'FAILED'  # keep last mask; flagged for a hand-set rect in overrides.json
            if m is None: m = np.zeros((sh, sw), np.uint8)
    m = _clean(m)
    mfull = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
    if method != 'FAILED': mfull = refine_hi(a, mfull)
    return mfull, method, (ok, why, tried)

# ---------- repair / clean / look ----------
def apply_repairs(a, ov):
    h, w, _ = a.shape
    for (l, t, r, b) in ov.get('repair', []):
        m = np.zeros((h, w), np.uint8); m[int(t*h):int(b*h), int(l*w):int(r*w)] = 255
        a = cv2.inpaint(a, m, 5, cv2.INPAINT_TELEA)
    for (sl, st, sr, sb, dl, dt) in ov.get('clone', []):
        x0, y0, x1, y1 = int(sl*w), int(st*h), int(sr*w), int(sb*h); pw, ph = x1-x0, y1-y0
        patch = a[y0:y1, x0:x1].copy(); cx, cy = int(dl*w)+pw//2, int(dt*h)+ph//2
        a = cv2.seamlessClone(patch, a, 255*np.ones(patch.shape[:2], np.uint8), (cx, cy), cv2.NORMAL_CLONE)
    return a

def clean_dust(a, fg, thr=40, maxarea=14):
    box = cv2.erode((fg > 127).astype(np.uint8), np.ones((7, 7), np.uint8))
    med = cv2.medianBlur(a, 7); d = np.abs(a.astype(np.int16)-med.astype(np.int16)).max(2)
    sp = ((d > thr) & (box > 0)).astype(np.uint8); n, lab, st, _ = cv2.connectedComponentsWithStats(sp)
    good = (st[:, 4] <= maxarea) & (np.maximum(st[:, 2], st[:, 3]) <= 5); good[0] = False       # one pass over the labels (was one full-image scan per speck: 80 s on textured paper)
    keep = good[lab].astype(np.uint8)
    if int(keep.sum()) > 5000: return a, -int(keep.sum())      # that many 'specks' is paper texture/weave, not dust: leave it alone (negative count = skipped)
    keep = cv2.dilate(keep, np.ones((3, 3), np.uint8)); out = cv2.inpaint(a, keep*255, 3, cv2.INPAINT_TELEA)
    return out, int(keep.sum())

def flatten(a, fg, strength=.65, tone=None):
    m = (fg > 127).astype(np.float32); lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32); L = lab[..., 0]
    ys, xs = np.where(m > 0); size = max(xs.max()-xs.min(), ys.max()-ys.min()); sg = max(15, size*.22)
    f = 8; hh, ww = L.shape; sm = (max(1, ww//f), max(1, hh//f))
    Ls = cv2.resize(L, sm, interpolation=cv2.INTER_AREA); ms = cv2.resize(m, sm, interpolation=cv2.INTER_AREA)
    num = cv2.GaussianBlur(Ls*ms, (0, 0), sg/f); den = cv2.GaussianBlur(ms, (0, 0), sg/f)+1e-4
    illum = cv2.resize(num/den, (ww, hh), interpolation=cv2.INTER_LINEAR); mean = (L*m).sum()/m.sum()
    L2 = np.clip(L*np.clip(mean/np.maximum(illum, 1), .8, 1.25)**strength, 0, 255)
    mean2 = (L2*m).sum()/m.sum(); med = float(np.median(L2[m > 0]))
    chroma = float(np.sqrt((lab[..., 1]-128)**2+(lab[..., 2]-128)**2)[m > 0].mean())
    dark_neutral = chroma <= 25 and med < 95; flatten.key = 50 if dark_neutral else 150
    if chroma > 25: tgt_med = med+(118-med)*.70 if med < 118 else med           # colorful box (red, green, orange): lift an under-exposed one, leave the rest
    elif dark_neutral: tgt_med = med*.92                                        # black / charcoal box: keep it deep, do not lift
    elif tone == 'white': tgt_med = max(med, med+(222-med)*.8)                  # override: this box is white, shot dim
    elif tone == 'silver': tgt_med = med                                        # override: metallic/gray box, keep its captured tone
    elif med > 125: tgt_med = med+(214-med)*float(np.clip(.25+(med-150)/40.0*.4, .25, .65))       # white box: clean light. Silver / light gray (median < 190) keep their metal tone
    else: tgt_med = med
    g = np.log(max(tgt_med, 1)/255)/np.log(max(med, 1)/255); L2 = 255*(L2/255)**np.clip(g, .70, 1.45)
    if dark_neutral:                                                            # true black point
        lo = min(np.percentile(L2[m > 0], .5), 8); L2 = np.clip((L2-lo*.9)*(255/max(255-lo*.9, 1)), 0, 255)
    hi = np.percentile(L2[m > 0], 99.5)
    if hi < 235 and tone != 'silver': L2 = np.clip(L2*(245/max(hi, 1)), 0, 255)*.5+L2*.5
    lab[..., 0] = np.clip(L2, 0, 255)
    return cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2RGB)

def pop(a):
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB); L = lab[..., 0]
    dk = getattr(flatten, 'key', 120) < 95; cw = .10 if dk else .15
    lab[..., 0] = cv2.addWeighted(L, 1-cw, cv2.createCLAHE(clipLimit=1.8, tileGridSize=(6, 6)).apply(L), cw, 0)
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB); hsv = cv2.cvtColor(out, cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[..., 1]/255; hsv[..., 1] = np.clip(hsv[..., 1]*(1+.38*(1-sat)**.7*np.clip((sat-.04)/.08, 0, 1)), 0, 255); hsv[..., 2] = np.clip(hsv[..., 2]*(1.0 if dk else 1.03), 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)

def polish(a, fg):
    """Adobe-style finish: pale lift, clarity (local contrast), gentle S-curve, output sharpen. All masked to the box."""
    m = (fg > 127); 
    if m.sum() < 100: return a
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32); L = lab[..., 0]
    chroma = float(np.sqrt((lab[..., 1]-128)**2+(lab[..., 2]-128)**2)[m].mean()); med = float(np.median(L[m]))
    key = getattr(flatten, 'key', 120)
    big = max(a.shape[:2]); r = max(8, big/60.0)             # clarity: large-radius unsharp on lightness
    mf = m.astype(np.float32); sc = 4.0/max(4.0, r/4.0); sz = (max(1, int(L.shape[1]*sc)), max(1, int(L.shape[0]*sc)))
    Ls = cv2.resize(L*mf, sz, interpolation=cv2.INTER_AREA); ms_ = cv2.resize(mf, sz, interpolation=cv2.INTER_AREA)       # blur over box pixels only, so backdrop never leaks into the box edge
    blur = cv2.resize(cv2.GaussianBlur(Ls, (0, 0), r*sc)/np.maximum(cv2.GaussianBlur(ms_, (0, 0), r*sc), 1e-3), (L.shape[1], L.shape[0]), interpolation=cv2.INTER_LINEAR)
    blur = np.where(m, blur, L); amt = .15 if key >= 95 else .12
    L = L+amt*(L-blur)
    x = np.clip(L/255, 0, 1); L = 255*np.clip(x+.9*x*(1-x)*(x-.5)*.5, 0, 1)   # mild S-curve
    lab[..., 0] = np.clip(L, 0, 255); out = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2RGB)
    of = out.astype(np.float32); bl = cv2.GaussianBlur(of*mf[..., None], (0, 0), 1.2)/np.maximum(cv2.GaussianBlur(mf, (0, 0), 1.2), 1e-3)[..., None]
    out = np.where(m[..., None], np.clip(of+.55*(of-bl), 0, 255), of).astype(np.uint8)
    return out

def edge_decolor(a, fg):
    """Pale boxes on a colored backdrop pick up a cyan/blue bounce strip on edges facing it. In a thin outer band, pull bright, lightly tinted blue-cyan pixels toward neutral."""
    h, w = fg.shape; m = (fg > 127).astype(np.uint8)
    _lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32); _mm = m > 0
    if np.median(_lab[..., 0][_mm]) < 195 or np.sqrt((_lab[..., 1]-128)**2+(_lab[..., 2]-128)**2)[_mm].mean() > 22: return a   # only white/near-white boxes
    k = max(9, int(max(h, w)*.022))
    band = (m - cv2.erode(m, np.ones((k, k), np.uint8))).astype(np.float32)
    band = np.clip(cv2.GaussianBlur(band, (0, 0), k/2.2)*1.8, 0, 1)*(m > 0)
    hsv = cv2.cvtColor(a, cv2.COLOR_RGB2HSV).astype(np.float32); H, S, V = hsv[..., 0]*2, hsv[..., 1]/255, hsv[..., 2]/255
    sel = ((H > 165) & (H < 255) & (S < .5) & (V > .55)).astype(np.float32); sel = cv2.GaussianBlur(sel, (0, 0), 2)
    wgt = (band*sel*.85)[..., None]; g = a.astype(np.float32).mean(2, keepdims=True)*np.ones((1, 1, 3), np.float32)
    return np.clip(a.astype(np.float32)*(1-wgt)+g*wgt, 0, 255).astype(np.uint8)

def snap_edge(a, fg, r=None):
    """Re-decide the mask inside a thin band around its outline using local colour models of the backdrop (outside) and the box (inside).
    Returns (mask, moved): moved = share of the band that changed; -1 = result rejected (area off by >15%), original mask returned."""
    m = (fg > 127).astype(np.uint8); h, w = m.shape
    if r is None: r = max(6, int(max(h, w)*.005))
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*r+1, 2*r+1))
    sure_fg = cv2.erode(m, ker); sure_bg = 1-cv2.dilate(m, ker); band = (sure_fg == 0) & (sure_bg == 0)
    if not band.any() or sure_fg.sum() < 100 or sure_bg.sum() < 100: return fg, 0.0
    y0, y1 = np.where(band.any(1))[0][[0, -1]]; x0, x1 = np.where(band.any(0))[0][[0, -1]]
    p = 6*r; y0, y1, x0, x1 = max(0, y0-p), min(h, y1+p+1), max(0, x0-p), min(w, x1+p+1)
    lab = cv2.cvtColor(cv2.GaussianBlur(a[y0:y1, x0:x1], (0, 0), 1.0), cv2.COLOR_RGB2LAB).astype(np.float32); lab[..., 0] *= .5
    def local(sel):
        s = sel[y0:y1, x0:x1].astype(np.float32); den = cv2.GaussianBlur(s, (0, 0), 2.0*r)
        return cv2.GaussianBlur(lab*s[..., None], (0, 0), 2.0*r)/np.maximum(den, 1e-4)[..., None], den
    cf, df = local(sure_fg); cb, db = local(sure_bg)
    d_f = np.sqrt(((lab-cf)**2).sum(2)); d_b = np.sqrt(((lab-cb)**2).sum(2))
    al = d_b/np.maximum(d_b+d_f, 1e-3)
    ok = (df > 1e-3) & (db > 1e-3) & (np.sqrt(((cf-cb)**2).sum(2)) > 12)        # only where box and backdrop really differ
    out = m.copy(); sub = out[y0:y1, x0:x1]; bsub = band[y0:y1, x0:x1] & ok
    sub[bsub] = (al[bsub] > .5).astype(np.uint8)
    out = cv2.morphologyEx(out, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)); out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, lb, st, _ = cv2.connectedComponentsWithStats(out, 8)
    if n > 2: out = (st[:, 4] >= .02*st[1:, 4].max())[lb].astype(np.uint8)*(lb > 0)
    moved = float((out != m).sum())/max(1, int(band.sum()))
    if not .85 < out.sum()/max(1, m.sum()) < 1.15: return fg, -1.0
    return (out*255).astype(np.uint8), moved

def edge_extend(a, fg, px=None):
    """Colour decontamination: repaint the outer few pixels of the box with colour pulled from just inside it, so no backdrop colour sits in the feathered edge."""
    m = (fg > 127).astype(np.uint8)
    if px is None: px = max(4, int(max(m.shape)*.002))
    d = cv2.distanceTransform(m, cv2.DIST_L2, 3)
    core = (d > px).astype(np.float32); f = a.astype(np.float32)
    den = cv2.GaussianBlur(core, (0, 0), px); fill = cv2.GaussianBlur(f*core[..., None], (0, 0), px)/np.maximum(den, 1e-4)[..., None]
    wgt = (np.clip(1-(d-1)/px, 0, 1)*(den > 1e-3))[..., None]         # 1 at/outside the outline -> 0 at px inside
    return np.clip(f*(1-wgt)+fill*wgt, 0, 255).astype(np.uint8)

def convex_fix(fg, min_solidity=.975):
    """Glossy edges that reflect the bright backdrop get cut out of the AI mask as dashes and notches. A box piece whose outline is already almost convex (solidity >= .975)
    is replaced by its convex hull, which restores straight edges and corners. Concave pieces (open lids, handles, sets) are left alone. Returns (mask, area_added_fraction)."""
    m = (fg > 127).astype(np.uint8); n, lb, st, _ = cv2.connectedComponentsWithStats(m, 8); out = m.copy(); added = 0
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] < 5000: continue
        c = (lb == i).astype(np.uint8); cs, _ = cv2.findContours(c, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cs: continue
        cc = max(cs, key=cv2.contourArea); hull = cv2.convexHull(cc); ha = cv2.contourArea(hull); ca = cv2.contourArea(cc)
        if ha > 0 and ca/ha >= min_solidity:
            h = np.zeros_like(m); cv2.fillPoly(h, [hull], 1); added += int((h > out).sum()); out = np.maximum(out, h)
    return (out*255).astype(np.uint8), added/max(1, int(m.sum()))

def smooth_fg(fg):
    """Removes the scalloped staircase on outlines: blur + re-threshold the mask (corners stay sharp at this radius)."""
    sg = max(2.5, max(fg.shape)*.0015); b = cv2.GaussianBlur(fg, (0, 0), sg)
    return ((b > 127)*255).astype(np.uint8)

def cast_fix(a, fg, prot=None):
    """Pale/neutral boxes shot on a colored backdrop keep a blue bounce cast. Remove the blue/cyan side of the tint only (cream stays warm, gray goes neutral)."""
    m = fg > 127; lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32); A, B = lab[..., 1]-128, lab[..., 2]-128
    ch = np.sqrt(A**2+B**2)
    if np.median(lab[..., 0][m]) < 150 or ch[m].mean() > 22: return a
    w = np.clip((30-ch)/12.0, 0, 1)*(prot if prot is not None else 1)       # only low-chroma pixels; real artwork colors are left alone
    lab[..., 2] = 128+B+np.maximum(-B, 0)*.85*w              # blue -> neutral (b* negative = blue)
    lab[..., 1] = 128+A+np.maximum(-A, 0)*.5*w               # cyan/green-ish -> toward neutral
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)

def gloss_fix(a, fg):
    """Glossy/laminated BLACK boxes mirror the blue backdrop and read blue/teal/purple-gray. Only for boxes that are mostly black: on dark pixels with a blue-side tint (b* < 0), pull the color toward neutral and deepen the haze. Colored artwork (green, red, orange...) and boxes that are not mostly black are untouched."""
    m = fg > 127; lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32); L, A, B = lab[..., 0], lab[..., 1]-128, lab[..., 2]-128
    ch = np.sqrt(A**2+B**2)
    if np.median(L[m]) > 85 or ch[m].mean() > 26: return a
    w = np.clip((130-L)/50.0, 0, 1)*np.clip((55-ch)/20.0, 0, 1)*np.clip(-B/6.0, 0, 1)*m
    w = cv2.GaussianBlur(w.astype(np.float32), (0, 0), 3)
    lab[..., 1] = 128+A*(1-.9*w); lab[..., 2] = 128+B*(1-.9*w)
    lab[..., 0] = np.clip(L*(1-.12*w), 0, 255)
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)

def haze_fix(a, fg, prot=None):
    """Glossy light surfaces (e.g. the top of a white panel) mirror the blue backdrop as a faint gray-green/cyan sheen. On LIGHT, nearly neutral pixels with a blue/cyan-side tint, pull the tint to neutral. Real pastel artwork has more color than this and is left alone."""
    m = fg > 127; lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32); L, A, B = lab[..., 0], lab[..., 1]-128, lab[..., 2]-128
    ch = np.sqrt(A**2+B**2)
    side = np.clip(((-B)/5.0), 0, 1).clip(0, 1) + np.clip(((-A)-2)/5.0, 0, 1)*np.clip((4-B)/4.0, 0, 1)     # blue side or green/cyan side tint
    w = np.clip((L-70)/35.0, 0, 1)*np.clip((26-ch)/10.0, 0, 1)*np.clip(side, 0, 1)*m
    if prot is not None: w = w*prot
    w = cv2.GaussianBlur(w.astype(np.float32), (0, 0), 4)
    lab[..., 1] = 128+A*(1-.85*w); lab[..., 2] = 128+B*(1-.85*w)
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)

def edge_define(a, fg):
    """White-on-white fix: bright box edges vanish on the white background. Cap blown highlights and darken a thin soft rim on bright edge pixels."""
    m = (fg > 127).astype(np.uint8); h, w = m.shape; k = max(5, int(max(h, w)*.0045))
    inner = (m - cv2.erode(m, np.ones((k, k), np.uint8))).astype(np.float32)
    rim = np.clip(cv2.GaussianBlur(inner, (0, 0), k*.7)*1.6, 0, 1)*(m > 0)
    f = a.astype(np.float32); L = f.mean(2)
    bright = np.clip((L-185)/45.0, 0, 1)
    f = f*(1-.15*rim*bright)[..., None]                     # soft darker rim only where the edge is bright
    top = 240.0; mx = f.max(2, keepdims=True); over = np.clip((mx-top)/(255-top), 0, 1)
    f = f*(1-.05*over)                                     # keep big flat whites just under paper-white
    return np.clip(f, 0, 255).astype(np.uint8)

def composite(a, fg):
    """Returns white-background composite, box bbox, and the soft mask + shadow alpha (for the transparent cutout)."""
    h, w, _ = a.shape; k = max(3, int(w*.0015)) | 1
    soft2 = np.clip((cv2.GaussianBlur(fg, (k*2+1, k*2+1), 0).astype(float)/255-.08)/.84, 0, 1)
    soft = soft2[..., None]
    ys, xs = np.where(fg > 127); yb = ys.max(); xl, xr = xs.min(), xs.max()
    bh = yb-ys.min(); band = max(4, int(bh*.05)); drop = max(3, int(bh*.012)); m = (fg > 127).astype(np.uint8)
    up = np.zeros_like(m); up[:-band] = m[band:]; edge = (m & (1-up)).astype(np.float32)
    edge = cv2.warpAffine(edge, np.float32([[1, 0, 0], [0, 1, drop]]), (w, h))
    sh2 = np.clip(cv2.GaussianBlur(edge, (0, 0), max(6, (xr-xl)*.012))*.55, 0, .30)*(1-soft2); sh = sh2[..., None]
    comp = np.clip(a*soft+(255*(1-sh)*np.ones_like(a, dtype=float))*(1-soft), 0, 255).astype(np.uint8)
    return comp, (xl, ys.min(), xr, yb), soft2, sh2

def _square_canvas(arr, bbox, pad, fill):
    h, w = arr.shape[:2]; l, t, r, b = bbox; side = max(r-l, b-t); half = int(side/2*(1+2*pad)); cx, cy = (l+r)//2, (t+b)//2
    ch = arr.shape[2] if arr.ndim == 3 else 1
    canvas = np.empty((half*2, half*2, ch), arr.dtype); canvas[:] = fill
    sx0, sy0 = cx-half, cy-half; x0, y0, x1, y1 = max(0, sx0), max(0, sy0), min(w, cx+half), min(h, cy+half)
    canvas[y0-sy0:y1-sy0, x0-sx0:x1-sx0] = arr[y0:y1, x0:x1].reshape(y1-y0, x1-x0, ch)
    return canvas

def despill(a, fg, ch, prot=None):
    """Colored backdrop (blue/green): pull the backdrop color out of the box. Full strength on the outline, gentle inside on near-neutral pixels."""
    f = a.astype(np.float32); o = [i for i in range(3) if i != ch]
    lim = np.maximum(f[..., o[0]], f[..., o[1]]); excess = np.maximum(f[..., ch]-lim, 0)
    fgb = (fg > 127).astype(np.uint8); k = max(9, int(max(a.shape[:2])*.012))
    band = (fgb - cv2.erode(fgb, np.ones((k, k), np.uint8))).astype(np.float32)
    band = cv2.GaussianBlur(band, (0, 0), k/3.0); band = np.clip(band*2.2, 0, 1)
    inner = .6*np.clip((40-excess)/24.0, 0, 1)          # (smooth ramp, no hard step)  near-neutral surfaces tinted by bounce light; real blue/green artwork (big excess) is left alone
    if prot is not None: inner = inner*prot
    if float((excess[fgb > 0] > 15).mean()) > .10: inner = inner*0          # box has real blue/green artwork: only strip the thin fringe, never the interior
    keepblue = np.clip((120-excess)/70.0, 0, 1)             # strongly blue/green ink (big excess) is real artwork: spare it, only strip the weak spill fringe
    w = np.maximum(band*keepblue, inner)*(fgb > 0)
    f[..., ch] = f[..., ch]-excess*w
    return np.clip(f, 0, 255).astype(np.uint8)

def run(src, out, long=2400, pad=.125, wide=False):
    """Writes OUT.jpg (master q90), OUT.webp, OUT-cut.png (transparent), and OUT-wide.jpg (3200x1800) when wide=True."""
    name = os.path.basename(src); ov = overrides(name)
    raw = load(src); problems = []; warn = []; fg = None; method = None; hole_frac = 0.0; mask_src = 'none'
    _mp = mask_path(src)
    if not ov.get('method') and not ov.get('rect'):          # AI cutout is the only normal path; anything else is flagged
        if not os.path.exists(_mp): problems.append('no AI mask')
        else:
            try:
                with Image.open(_mp) as _mi: _m = np.array(_mi.convert('L'))      # PIL, not cv2.imread: cv2 cannot open non-ASCII paths on Windows
            except (OSError, SyntaxError): _m = None
            if _m is None: problems.append('AI mask unreadable')
            elif abs(_m.shape[1]/_m.shape[0]-raw.shape[1]/raw.shape[0]) > .02: problems.append('AI mask shape does not match the photo (remake the mask)')
            else:
                _m = cv2.resize(_m, (raw.shape[1], raw.shape[0]), interpolation=cv2.INTER_CUBIC); fg = ((_m > 127)*255).astype(np.uint8)
                _n, _lb, _st, _ = cv2.connectedComponentsWithStats((fg > 0).astype(np.uint8), 8)
                if _n > 2:                    # keep every real piece (lid beside base, sets); specks under 4% of the biggest piece are dropped
                    _keep = _st[:, cv2.CC_STAT_AREA] >= .04*_st[1:, cv2.CC_STAT_AREA].max(); _keep[0] = False
                    fg = (_keep[_lb]*255).astype(np.uint8)
                    if int(_keep.sum()) > 1: warn.append('%d separate pieces kept' % int(_keep.sum()))
                _fr = float((fg > 0).mean())
                if not .015 < _fr < .75: problems.append('ai mask area %.3f' % _fr); fg = None
                else:
                    _cs, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)       # B2: fill interior holes (white art read as backdrop)
                    _filled = np.zeros_like(fg); cv2.drawContours(_filled, _cs, -1, 255, cv2.FILLED)
                    hole_frac = float(((_filled > 0) & (fg == 0)).sum())/max(1, int((fg > 0).sum()))
                    if not ov.get('see_through'): fg = _filled        # "see_through": true in overrides.json only for a real open window
                    if hole_frac > .15: problems.append('holes %.1f%% of box: check the cutout' % (hole_frac*100))
                    elif hole_frac > .002: warn.append('holes %.1f%% filled' % (hole_frac*100))
                    fg, _hadd = convex_fix(fg)
                    if _hadd > .004: warn.append('edge notches closed (+%.1f%% area)' % (_hadd*100))
                    _y, _x = np.where(fg > 0); _sh, _sw = fg.shape
                    if _x.min() < _sw*.01 or _x.max() > _sw*.99 or _y.min() < _sh*.01 or _y.max() > _sh*.99: problems.append('touches frame edge')
                    method = 'isnet'; mask_src = 'ai'
    if fg is None:
        a = apply_repairs(wb(raw), ov)
        fg, method, (_ok2, _why2, tried) = mask_box(a, ov.get('rect'), ov.get('method'), ov.get('cut'))
        mask_src = 'rules'
        if not _ok2: problems.append(_why2)
    if ov.get('trim'):   # keep only this part of the found box (fractions of its own bounding box: left, top, right, bottom); cuts a stray strip
        _y, _x = np.where(fg > 127); bl, br, bt, bb = _x.min(), _x.max(), _y.min(), _y.max(); tl, tt, tr, tb = ov['trim']; keep = np.zeros_like(fg)
        keep[int(bt+(bb-bt)*tt):int(bt+(bb-bt)*tb)+1, int(bl+(br-bl)*tl):int(bl+(br-bl)*tr)+1] = 1; fg = fg*keep
    fg = smooth_fg(fg)
    if ov.get('keystone'):                       # straight-on face shot from a slight angle: warp the 4-corner outline back to a rectangle
        _cs, _ = cv2.findContours((fg > 127).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE); _c = max(_cs, key=cv2.contourArea)
        _q = cv2.approxPolyDP(_c, .02*cv2.arcLength(_c, True), True)
        if len(_q) == 4:
            _q = _q.reshape(4, 2).astype(np.float32); _s = _q.sum(1); _d = np.diff(_q, axis=1).ravel()
            _o = np.array([_q[np.argmin(_s)], _q[np.argmin(_d)], _q[np.argmax(_s)], _q[np.argmax(_d)]], np.float32)       # tl, tr, br, bl
            _w = (np.linalg.norm(_o[1]-_o[0])+np.linalg.norm(_o[2]-_o[3]))/2; _h = (np.linalg.norm(_o[3]-_o[0])+np.linalg.norm(_o[2]-_o[1]))/2
            _cx, _cy = _q[:, 0].mean(), _q[:, 1].mean(); _dst = np.array([[_cx-_w/2, _cy-_h/2], [_cx+_w/2, _cy-_h/2], [_cx+_w/2, _cy+_h/2], [_cx-_w/2, _cy+_h/2]], np.float32)
            _M = cv2.getPerspectiveTransform(_o, _dst); _hh, _ww = fg.shape
            raw = cv2.warpPerspective(raw, _M, (_ww, _hh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            fg = ((cv2.warpPerspective(fg, _M, (_ww, _hh), flags=cv2.INTER_LINEAR) > 127)*255).astype(np.uint8)
        else: problems.append('keystone: outline is not a 4-corner shape')
    ys, xs = np.where(fg > 127); H, W = fg.shape
    box_px = int(max(xs.max()-xs.min(), ys.max()-ys.min())+1)
    if box_px < 1500: problems.append('box only %d px (enlarged too much)' % box_px)
    elif box_px < 1900: warn.append('box %d px (enlarged %.2fx)' % (box_px, 1920/box_px))
    _rin = raw[fg > 127]; blown_in = float((_rin.min(1) >= 250).mean()) if len(_rin) else 0.0      # lost highlights are measured on the INPUT (edge_define hides them later)
    if blown_in > .10: problems.append('%.1f%% of box blown out in the original photo' % (blown_in*100))
    elif blown_in > .01: warn.append('%.1f%% of box blown out in the original' % (blown_in*100))
    med, clean = backdrop_sample(raw, fg)                          # B8: backdrop color from the border outside the mask, one sample for wb and spill
    if med is None:
        problems.append('backdrop not measurable (%.1f%% clean)' % (clean*100)); a = apply_repairs(wb(raw), ov)
        _t = np.median(a[:int(a.shape[0]*.12), int(a.shape[1]*.25):int(a.shape[1]*.75)].reshape(-1, 3), 0)
    else:
        a = apply_repairs(wb(raw, med), ov); _t = med
    spill = int(np.argmax(_t)) if _t.max()-_t.min() > 40 else None
    l, r, t, b = xs.min(), xs.max(), ys.min(), ys.max(); side = max(r-l, b-t); P = int(side*(pad+.12))
    cx, cy = (l+r)//2, (t+b)//2; half = side//2+P
    L, R, T, B = max(0, cx-half), min(W, cx+half), max(0, cy-half), min(H, cy+half)
    a, fg = a[T:B, L:R], fg[T:B, L:R]
    k = 3200/max(a.shape[:2])
    if k < 1: a = cv2.resize(a, None, fx=k, fy=k, interpolation=cv2.INTER_AREA); fg = cv2.resize(fg, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR)
    fg0_area = int((fg > 127).sum())
    fg, edge_moved = snap_edge(a, fg) if not os.environ.get('KY_NOSNAP') else (fg, 0.0)
    snap_area = int((fg > 127).sum())
    if edge_moved < 0: warn.append('outline check rejected (area changed >15%): AI outline kept')
    elif edge_moved > .30: warn.append('AI mask was loose: outline moved in %.0f%% of the edge band' % (edge_moved*100))
    if spill is not None:
        if not os.environ.get('KY_NOERODE'): fg = cv2.erode(fg, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))   # trim the thin backdrop-colored fringe at the outline
        _c0 = _chroma(a, fg > 127)
        _pr = art_protect(a, fg)
        a = despill(a, fg, spill, _pr); a = edge_decolor(a, fg); a = cast_fix(a, fg, _pr); a = haze_fix(a, fg, _pr)      # gloss_fix removed (B4): it turned real navy/blue art black
        _c1 = _chroma(a, fg > 127)
        if _c0 >= 8 and _c1 < .75*_c0: problems.append('color strength dropped %.0f%% (%.1f->%.1f)' % ((1-_c1/_c0)*100, _c0, _c1))
    a, nd = clean_dust(a, fg); a = flatten(a, fg, tone=ov.get('tone')); a = pop(a); a = polish(a, fg); a = edge_define(a, fg)
    _px = a[fg > 127]; clip_frac = float(((_px.max(1) <= 4) | (_px.min(1) >= 251)).mean()) if len(_px) else 0.0
    if clip_frac > .05: problems.append('%.1f%% of box pure black/white' % (clip_frac*100))
    ok = not problems; why = '; '.join(problems) or 'ok'
    a = edge_extend(a, fg)
    comp, bbox, soft, sh = composite(a, fg)
    # --- master (white background)
    can = _square_canvas(comp, bbox, pad, 255)
    im = Image.fromarray(can).resize((long, long), Image.LANCZOS)
    _atomic(im, out+'.jpg', 'JPEG', quality=90, optimize=True, progressive=True, subsampling=0); _atomic(im, out+'.webp', 'WEBP', quality=82, method=4)
    # --- transparent cutout (shadow kept as faint black alpha)
    alpha = np.clip(soft+sh*(1-soft), 0, 1); col = np.where(alpha[..., None] > 1e-3, (a*soft[..., None])/np.maximum(alpha[..., None], 1e-3), 0)
    rgba = np.dstack([np.clip(col, 0, 255), alpha*255]).astype(np.uint8)
    cut = _square_canvas(rgba, bbox, pad, np.array([255, 255, 255, 0], np.uint8))
    cim = Image.fromarray(cut, 'RGBA').resize((long, long), Image.LANCZOS)
    _atomic(cim, out+'-cut.png', 'PNG', compress_level=3)
    # --- wide hero 3200x1800: product in the right 55%, left 45% clean
    if wide:
        cw, chh = 3200, 1800; bgc = (242, 243, 245)
        l2, t2, r2, b2 = bbox; sc = min(0.78*chh/max(1, (b2-t2)), 0.50*cw/max(1, (r2-l2)))
        pad_px = int(max(r2-l2, b2-t2)*.08); x0, y0, x1, y1 = max(0, l2-pad_px), max(0, t2-pad_px), min(rgba.shape[1], r2+pad_px), min(rgba.shape[0], b2+pad_px)
        crop = Image.fromarray(np.dstack([np.clip(col[y0:y1, x0:x1], 0, 255), alpha[y0:y1, x0:x1]*255]).astype(np.uint8), 'RGBA')
        crop = crop.resize((max(1, int(crop.width*sc)), max(1, int(crop.height*sc))), Image.LANCZOS)
        bg = Image.new('RGBA', (cw, chh), bgc+(255,)); cxw = int(cw*(.45+.55/2)); cyw = int(chh*.52)
        bg.alpha_composite(crop, (cxw-crop.width//2, cyw-crop.height//2)); _atomic(bg.convert('RGB'), out+'-wide.jpg', 'JPEG', quality=88, optimize=True, progressive=True)
    return {'file': name, 'size': im.size, 'cutout': method, 'qc_ok': bool(ok), 'qc': why, 'engine': ENGINE, 'warn': '; '.join(warn), 'mask_src': mask_src, 'hole_frac': round(hole_frac, 4), 'box_px': box_px, 'clip_frac': round(clip_frac, 4), 'edge_moved': round(edge_moved, 3), 'areas': [fg0_area, snap_area, int((fg > 127).sum())], 'blown_in': round(blown_in, 4), 'backdrop_clean': round(clean, 3), 'dust_px': nd, 'repairs': len(ov.get('repair', []))+len(ov.get('clone', [])), 'wide': bool(wide)}

def maskcheck(d, outp):
    fs = sorted(glob.glob(os.path.join(d, '*', '*.jpg'))); T = 300; cols = 8; rows = (len(fs)+cols-1)//cols
    sheet = Image.new('RGB', (cols*T, rows*(T+14)), 'white'); from PIL import ImageDraw; dr = ImageDraw.Draw(sheet); rep = []
    for i, f in enumerate(fs):
        a = wb(load(f)); h, w, _ = a.shape; sc = 600/max(h, w); s = cv2.resize(a, (int(w*sc), int(h*sc)), interpolation=cv2.INTER_AREA)
        ov = overrides(os.path.basename(f)); m, method, (ok, why, tried) = mask_box(s, ov.get('rect'), ov.get('method'), ov.get('cut'))
        ov_img = s.copy(); cs, _ = cv2.findContours((m > 127).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(ov_img, cs, -1, (255, 0, 0) if not ok else (0, 200, 0), 3)
        im = Image.fromarray(ov_img); im.thumbnail((T, T)); x, y = (i % cols)*T, (i//cols)*(T+14); sheet.paste(im, (x, y+14))
        dr.text((x+2, y+1), f"{i} {os.path.basename(os.path.dirname(f))[:14]} {method}{'' if ok else ' !'+why[:18]}", fill='red' if not ok else 'black')
        rep.append((i, f, method, ok, why))
    sheet.save(outp, quality=85)
    for r in rep:
        if not r[3]: print('CHECK', r)
    print('masks ok:', sum(1 for r in rep if r[3]), '/', len(rep))

if __name__ == '__main__':
    if sys.argv[1] == '--maskcheck': maskcheck(sys.argv[2], sys.argv[3])
    else: print(run(sys.argv[1], sys.argv[2], wide='--wide' in sys.argv))

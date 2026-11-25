import sys,os,numpy as np,cv2; sys.path.insert(0,'site/tools'); import post_edit as P
s,f=sys.argv[1],sys.argv[2]; src='PHOTOS/1-ORIGINALS/%s/%s'%(s,f); raw=P.load(src)
m=cv2.resize(cv2.imread(P.mask_path(src),0),(raw.shape[1],raw.shape[0]));fg=((m>127)*255).astype(np.uint8)
cs,_=cv2.findContours(fg,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);fl=np.zeros_like(fg);cv2.drawContours(fl,cs,-1,255,-1);fg=P.smooth_fg(fl)
med,_=P.backdrop_sample(raw,fg);print('backdrop',med)
a=P.wb(raw,med);k=1600/max(a.shape);a=cv2.resize(a,None,fx=k,fy=k,interpolation=cv2.INTER_AREA);fg=cv2.resize(fg,(a.shape[1],a.shape[0]))
fg=cv2.erode(fg,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5)));M=fg>127
print('start',P._chroma(a,M));ch=int(np.argmax(med))
for n,fn in(('despill',lambda x:P.despill(x,fg,ch)),('edge_decolor',lambda x:P.edge_decolor(x,fg)),('cast_fix',lambda x:P.cast_fix(x,fg)),('haze_fix',lambda x:P.haze_fix(x,fg))):
    a=fn(a);print(n,P._chroma(a,M))
print('--- variants')
a0=P.wb(raw,med);a0=cv2.resize(a0,None,fx=k,fy=k,interpolation=cv2.INTER_AREA)
f=a0.astype(np.float32);o=[i for i in range(3) if i!=ch];lim=np.maximum(f[...,o[0]],f[...,o[1]]);ex=np.maximum(f[...,ch]-lim,0)
fgb=(fg>127).astype(np.uint8);kk=max(9,int(max(a0.shape[:2])*.012));band=(fgb-cv2.erode(fgb,np.ones((kk,kk),np.uint8))).astype(np.float32);band=np.clip(cv2.GaussianBlur(band,(0,0),kk/3.0)*2.2,0,1)
inner=(ex<28).astype(np.float32)*.6
for n,w in(('band only',band),('inner only',inner),('both',np.maximum(band,inner))):
    g=f.copy();g[...,ch]=g[...,ch]-ex*w*fgb;print(n,P._chroma(np.clip(g,0,255).astype(np.uint8),M))
print('ex pctl in box',np.percentile(ex[M],[10,50,75,90,99]))

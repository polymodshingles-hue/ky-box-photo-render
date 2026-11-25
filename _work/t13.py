import sys,os,json,time
sys.path.insert(0,'site/tools'); import post_edit as P
items=json.load(open('_work/t13_items.json')); k=int(sys.argv[1]); n=int(sys.argv[2])
for i,(s,f) in enumerate(items):
    if i%n!=k: continue
    os.makedirs('_work/t13/'+s,exist_ok=True); t=time.time()
    r=P.run('PHOTOS/1-ORIGINALS/%s/%s'%(s,f),'_work/t13/%s/%s'%(s,os.path.splitext(f)[0]))
    print(s,f[-12:],r['qc_ok'],r['qc'],r['dust_px'],round(time.time()-t),flush=True)

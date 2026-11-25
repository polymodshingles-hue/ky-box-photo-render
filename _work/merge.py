import json
parts=json.load(open('_work/processed/parts.json')); base=json.load(open('_work/processed/report.json'))
for i,pl in enumerate(parts):
    r=json.load(open('_work/processed/report_p%d.json'%i))
    for k,v in r.items():
        if k.split('/')[0] in pl: base[k]=v
tmp='_work/processed/report.json.tmp'; json.dump(base,open(tmp,'w'),indent=1)
import os; os.replace(tmp,'_work/processed/report.json')
for i in range(3): json.dump(base,open('_work/processed/report_p%d.json'%i,'w'))
from collections import Counter; print(len(base),Counter(v['status'] for v in base.values()))

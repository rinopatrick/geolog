#!/usr/bin/env python3
import requests, json, sys
BASE='http://localhost:8000'

# write endpoints should reject viewer
endpoints=[
 ('POST','/api/wells/4/compute-sw',{'rw':0.1,'a':1,'m':2,'n':2}),
 ('POST','/api/wells/4/multimineral',{}),
 ('POST','/api/wells/4/permeability-multi',{'rw':0.1}),
 ('POST','/api/wells/4/vcl-enhanced',{}),
 ('POST','/api/wells/4/dual-water',{'rw':0.1}),
]
fail=[]
for m,p,b in endpoints:
    r=requests.post(BASE+p,headers={'X-User-Role':'viewer','Content-Type':'application/json'},json=b,timeout=30)
    if r.status_code not in (401,403):
        fail.append((p,r.status_code,r.text[:120]))
print(json.dumps({'checked':len(endpoints),'failed':len(fail)},indent=2))
for x in fail: print('FAIL',x)
sys.exit(1 if fail else 0)

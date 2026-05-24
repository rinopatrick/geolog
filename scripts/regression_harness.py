#!/usr/bin/env python3
import requests, sys, json
BASE = 'http://localhost:8000'
H = {'X-User-Role':'interpreter','Content-Type':'application/json'}

def get_well_id():
    r=requests.get(f"{BASE}/api/wells/",headers=H,timeout=10); r.raise_for_status()
    wells=r.json();
    if not wells: raise RuntimeError('No wells found')
    return wells[0]['id']

def run():
    wid=get_well_id()
    checks=[
      ('GET',f'/api/health',None),
      ('GET',f'/api/wells/',None),
      ('GET',f'/api/wells/{wid}',None),
      ('GET',f'/api/wells/{wid}/log-runs',None),
      ('GET',f'/api/wells/{wid}/tops',None),
      ('GET',f'/api/wells/{wid}/zones',None),
      ('GET',f'/api/wells/{wid}/report',None),
      ('GET',f'/api/wells/{wid}/data-table',None),
      ('GET',f'/api/wells/{wid}/zone-stats',None),
      ('POST',f'/api/wells/{wid}/compute-sw',{'rw':0.1,'a':1,'m':2,'n':2}),
      ('POST',f'/api/wells/{wid}/multimineral',{}),
      ('POST',f'/api/wells/{wid}/permeability-multi',{'rw':0.1}),
      ('POST',f'/api/wells/{wid}/vcl-enhanced',{}),
      ('POST',f'/api/wells/{wid}/dual-water',{'rw':0.1}),
      ('POST',f'/api/wells/{wid}/electrofacies',{'n_clusters':3}),
      ('POST',f'/api/wells/{wid}/rw-estimation',{}),
      ('POST',f'/api/wells/{wid}/vcl-models',{}),
      ('POST',f'/api/wells/{wid}/tornado',{}),
      ('POST',f'/api/wells/{wid}/probability-plot',{}),
      ('POST',f'/api/wells/{wid}/moveable-oil',{}),
      ('GET',f'/api/wells/{wid}/export-las',None),
      ('GET',f'/api/wells/{wid}/report-pdf',None),
      ('GET',f'/api/projects/',None),
      ('GET',f'/api/templates',None),
      ('GET',f'/api/curve-config',None),
      ('GET',f'/api/jobs',None),
    ]
    passed=failed=0
    bad=[]
    for m,p,b in checks:
        try:
            if m=='GET': r=requests.get(BASE+p,headers=H,timeout=30)
            else: r=requests.post(BASE+p,headers=H,json=b,timeout=60)
            if r.status_code==200:
                passed+=1
            else:
                failed+=1; bad.append((m,p,r.status_code,r.text[:120]))
        except Exception as e:
            failed+=1; bad.append((m,p,'EXC',str(e)))
    print(json.dumps({'passed':passed,'failed':failed,'total':passed+failed},indent=2))
    for b in bad: print('FAIL',b)
    return 1 if failed else 0

if __name__=='__main__':
    sys.exit(run())

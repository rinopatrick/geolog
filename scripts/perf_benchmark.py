#!/usr/bin/env python3
import requests, time, json
BASE='http://localhost:8000'
H={'X-User-Role':'interpreter'}

def wid():
    return requests.get(f"{BASE}/api/wells/",headers=H,timeout=10).json()[0]['id']

w=wid()
runs=requests.get(f"{BASE}/api/wells/{w}/log-runs",headers=H,timeout=10).json()
rid=runs[-1]['id']
for n in [1000,5000,20000,100000]:
    t0=time.perf_counter()
    r=requests.get(f"{BASE}/api/log-runs/{rid}/data-decimated?max_points={n}",headers=H,timeout=120)
    dt=time.perf_counter()-t0
    ok=(r.status_code==200)
    print(json.dumps({'max_points':n,'ok':ok,'status':r.status_code,'sec':round(dt,3)}))

# Well upload (LAS)

## Sub-features

- Single LAS file upload to an existing well (`POST /api/wells/{wid}/upload-las`).
- Bulk multi-file import wizard. DLIS/LIS variants (same flow, different endpoint).

## How to get to it (user POV)

Wells view → pick a well → upload panel → choose `.las` file → curves appear in
curve inventory. Sample LAS files live in `test_data/*.las`.

## Driving it with HTTP

Auth: every write needs `-H "X-User-Role: admin"` (header-trust mode, dev/test only).
Project first — wells belong to a project:

```bash
B=http://127.0.0.1:8137
H='-H "X-User-Role: admin"'
PID=$(curl -sf -X POST $B/api/projects/ -H 'Content-Type: application/json' $H -d '{"name":"verify-proj"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
WID=$(curl -sf -X POST $B/api/wells/ -H 'Content-Type: application/json' $H -d "{\"project_id\":$PID,\"name\":\"verify-well\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
```

```bash
UP=$(curl -sf -F "file=@test_data/kgs_culwell_unit4_32_density_neutron_resistivity.las" $H \
  $B/api/wells/$WID/upload-las)
LRID=$(echo "$UP" | python3 -c "import sys,json; print(json.load(sys.stdin)['log_run_id'])")
# curves live under the log run, NOT /api/wells/{id}/curves (no such route):
curl -sf $H $B/api/log-runs/$LRID/curves | python3 -c "import sys,json; print(len(json.load(sys.stdin)), 'curves')"
```

## Gotchas

- Auth is header-trust in dev/test; no token needed on the verify instance.
- `~A` columns are positional; duplicate mnemonics kept under vendor name. Parse
  warnings returned in upload response, not as errors.
- Upload is synchronous for small files; large LAS may return a job id — poll
  `/api/ops/jobs/{id}` then.

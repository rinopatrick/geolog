# Reports export

## Sub-features

- Zonation report (gross/net per zone).
- PDF export incl. combined rock-type/TOC and custom report-builder templates
  (`/api/wells/{wid}` reports router, `/api/report-templates`).

## How to get to it (user POV)

Reports panel → pick well + template → build → download PDF.
`app.switchView('reportbuilder')`.

## Driving it with HTTP

```bash
B=http://127.0.0.1:8137
H='-H "X-User-Role: admin"'
# templates: create with sections (NOT config), list, then build PDF:
curl -sf -X POST $B/api/report-templates -H 'Content-Type: application/json' $H \
  -d '{"name":"verify-t","sections":["zonation","curves"]}'
curl -sf $H $B/api/report-templates/ | tee artifacts/verify/<ts>/templates.json
curl -sf $H "$B/api/wells/$WID/report-pdf?wid=$WID" -o artifacts/verify/<ts>/report.pdf
file artifacts/verify/<ts>/report.pdf  # must say PDF document
```

Route notes: list/create live at `/api/report-templates` (empty list `[]` on a
fresh DB is valid, not an error); zonation stats at
`GET /api/wells/{wid}/zone-stats?wid={wid}`.

## Gotchas

- PDF generation may need system libs; if missing on verify host, record the exact
  error in drive.log and mark the journey blocked (do not fake with HTML).
- Template CRUD is separate (`report_templates.py`); verify template list
  non-empty before building.

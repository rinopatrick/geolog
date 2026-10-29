# Report builder

Templates store a name, title and selected sections:

```json
{
  "name": "Field review",
  "title": "GeoLog Well Report",
  "sections": ["rock_source", "zonation", "production", "qc", "curves"]
}
```

## Endpoints

- `GET /api/report-templates`
- `POST /api/report-templates`
- `PUT /api/report-templates/{id}`
- `DELETE /api/report-templates/{id}` (admin)
- `POST /api/wells/{wid}/report/custom.pdf`

The PDF endpoint accepts either `{"template_id": 3}` or an inline
`{"title": "...", "sections": [...]}`. Sections without data are rendered as a
short note, not an error.

## Sections

- `rock_source`: Winland classes, R35/FZI and latest TOC/VKER stats.
- `zonation`: saved zones with gross intervals and total.
- `production`: latest rate, decline model and deterministic EUR.
- `qc`: advanced QC score, rating and issue counts.
- `curves`: curve inventory for the largest log run.

Templates are global in this version; per-user and per-project templates belong
with the multi-user workspace work.

# Core / SCAL

The core module stores routine and special core analysis, derives FZI flow
units, and fits/applies saturation-height models.

## Data model

- `core_datasets` — versioned, draft/approved container.
- `core_plugs` — well, name, MD/TVD, porosity, air/Klinkenberg perm, grain density, rock type.
- `core_measurements` — RCA/SCAL scalar measurements.
- `capillary_pressure` — `[[Pc, Sw], ...]` plus sigma/cos θ.
- `relative_perm` — `[[Sw, Kro, Krw], ...]`.
- `core_photos`, `thin_sections` — artifact path + metadata/checksum; files are not stored in SQLite.
- `rock_types`, `flow_units`, `contacts`, `saturation_height_models`.

Approved datasets are immutable. A new import creates a new dataset version.

## API

```text
GET/POST  /api/wells/{wid}/core/plugs
GET/PUT/DELETE /api/wells/{wid}/core/plugs/{id}
POST      /api/wells/{wid}/core/plugs/{id}/measurements
POST      /api/wells/{wid}/core/plugs/{id}/capillary-pressure
POST      /api/wells/{wid}/core/plugs/{id}/relative-perm
POST      /api/wells/{wid}/core/plugs/{id}/photos
POST      /api/wells/{wid}/core/plugs/{id}/photos/upload
POST      /api/wells/{wid}/core/plugs/{id}/thin-sections
POST      /api/wells/{wid}/core/plugs/{id}/thin-sections/upload
POST      /api/wells/{wid}/core/plugs/{id}/depth-match
GET       /api/wells/{wid}/core/plugs/{id}/depth-matches
POST      /api/wells/{wid}/core/depth-matches/{id}/apply
POST      /api/wells/{wid}/core/import?dry_run=true|false&update=false
GET       /api/wells/{wid}/core/datasets
POST      /api/wells/{wid}/core/datasets/{id}/approve
GET/POST  /api/wells/{wid}/core/rock-types
GET/POST  /api/wells/{wid}/core/contacts
GET/POST  /api/wells/{wid}/core/flow-units
POST      /api/wells/{wid}/core/flow-units/cluster
POST      /api/wells/{wid}/core/saturation-height/fit
POST      /api/wells/{wid}/core/saturation-height/apply
GET       /api/wells/{wid}/core/saturation-height/models
POST      /api/wells/{wid}/core/saturation-height/models/{id}/approve
```

## Import

CSV or XLSX columns: `plug_name, depth_md, depth_tvd, formation, lithology, porosity,
perm_air, perm_klin, grain_density, fluid_saturation, plug_type, source, notes`.
`dry_run=true` validates without writing. Existing `(well, plug_name, depth_md)`
rows are conflicts unless `update=true`.

XLSX/XLSM is parsed with openpyxl. Depth matching is staged per plug:
`depth-match` creates a proposed match and `depth-matches/{id}/apply` copies its
`log_md` to `core_plugs.matched_log_md`. There is no automatic core-to-log
correlation yet.

## Flow units

`POST /core/flow-units/cluster` computes FZI:

```text
FZI = 0.0314 * sqrt(k/phi) / (phi / (1 - phi))
```

It sorts log-FZI and recursively splits the largest gap until `k` clusters
(a deterministic multi-resolution grouping). Each cluster is stored as a new
`flow_units` version. This is not the full MRGC/Facimage algorithm.

## Saturation height

Supported models: J-function, Brooks-Corey, Lambda, Thomeer and
Skelt-Harrison.

The J-function is:

```text
J = (Pc * sqrt(k/phi)) / (sigma * cos theta)
Sw = a * J^b
```

`fit` stores model parameters, R², residual and an input hash as a draft
`saturation_height_models` row. `apply` uses the selected contact/FWL, a default
0.433 psi/ft gradient, and `PHIE`/`PERM` curves; it returns Sw. The UI exposes
model type, fit and apply controls.

Photo and thin-section binaries can be uploaded to the artifact store:
`photos/upload` and `thin-sections/upload` (50 MB, image extensions).

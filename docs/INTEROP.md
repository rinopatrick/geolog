# WITSML and OSDU interoperability

Read-first adapters. Credentials are read from the environment, never stored in
the database or returned by the API.

## Configuration

```bash
GEOLOG_WITSML_URL=https://witsml.example/Store/Store.asmx
GEOLOG_WITSML_USER=...
GEOLOG_WITSML_PASSWORD=...
# or
GEOLOG_WITSML_TOKEN=...
GEOLOG_WITSML_TIMEOUT=30
GEOLOG_INTEROP_INSECURE_TLS=0   # 1 only for a controlled test endpoint

GEOLOG_OSDU_URL=https://osdu.example
GEOLOG_OSDU_TOKEN=...
GEOLOG_OSDU_PARTITION=...
GEOLOG_OSDU_WELLBORES_PATH=/api/wellbore/v1/wellbores
```

## WITSML 1.4.1.1

`WMLS_GetFromStore` over SOAP is implemented for `well` and `log` objects.
`pull` imports wells into one GeoLog project and can import log curves:

```text
POST /api/interop/witsml/test
POST /api/interop/witsml/pull?project_id=1&object_type=well|log|both
     &name=<object name>&well_id=<existing well id>&import_curves=true
```

Log curve mnemonics/units are preserved; values are stored as float64 arrays.
Duplicate log filenames (`witsml::<name>`) are skipped, not overwritten.

## OSDU Wellbore DDMS

```text
POST /api/interop/osdu/test
POST /api/interop/osdu/pull?project_id=1&limit=100
POST /api/interop/osdu/push/wells/{wid}
```

OSDU pulls `results` from the Wellbore DDMS collection and upserts wells by UWI
or name. Push sends a `master-data--Wellbore:1.0.0` record to the configured
collection. Log-curve pull/push is not implemented.

## Limits

- WITSML 2.1/ETP is not enabled; 1.4.1.1 SOAP is the supported path.
- No background sync, conflict resolution or incremental cursors.
- OSDU push does not allocate legal tags, ACLs or parents.
- The adapters use `urllib`; no vendor SDK is required.
- TLS verification is on unless `GEOLOG_INTEROP_INSECURE_TLS=1`.

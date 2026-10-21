# GeoLog #16 — WITSML/OSDU integration architecture
**Decision memo.** Issue text was not present in the repo; this addresses the supplied brief. Repo state: commit `a70be4e`, no WITSML/OSDU code.
## Recommendation
Build a **read-first, adapter-isolated integration**, not a sync engine.
1. **Phase 1:** WITSML **1.4.1.1** over SOAP `GetFromStore`, plus OSDU Wellbore DDMS REST pull and explicit push.
2. **Phase 2:** WITSML **2.1 over ETP 1.2** as a second adapter.
3. **Do not implement WITSML 2.0-only.** It is legacy; Energistics says 2.0 is "no longer recommended", 2.1 is current (May 2022) and requires ETP 1.2 [1]. The 1.4.1.1 installed base is larger, so it ships first [1][4].
4. GeoLog stays the interpretation system. Pull acquired data; push curated outputs only on explicit user action.
## Standards facts that drive the design
- **1.4.1.1:** 27 data objects; SOAP STORE API; identity is hierarchical — `uid` plus `uidWell`/`uidWellbore` [1][4]. A log is one curve group with `logCurveInfo` and `logData` [17].
- **2.x:** CTA object model; SOAP replaced by ETP; Log redesigned into Log → ChannelSet → Channel, where Channel ≈ 1.4.1.1 `logCurveInfo` [2][3].
- **ETP 1.2:** WebSocket, JSON-defined messages, Avro-subset serialization, JWT authentication, asynchronous sub-protocols [5]; spec doc v1.2 published 2024-07-31 [6].
- **OSDU:** Storage records carry a semver `kind`, ACLs, and `legal.legaltags`; Storage validates legal tags at ingest and refuses data without a valid one [7][8]. Bulk curve data lives in the DDMS, addressed by a Storage record; Wellbore DDMS v3 exposes wells, wellbores, welllogs, markersets, intervalsets, and chunked write sessions [10][11]. Records are versioned; supplying a version triggers optimistic locking [7].
## Mapping (v1)
| GeoLog | WITSML 1.4.1.1 | OSDU |
|---|---|---|
| Project | server/store context | partition + legal/ACL defaults, not a record |
| Well | `well` | `master-data--Well` |
| *(no wellbore table)* | `wellbore` | `master-data--Wellbore` (`WellID`, `FacilityName`) [15] |
| LogRun | `log` | `work-product-component--WellLog` |
| Curve | `logCurveInfo` | `WellLog.Curves[]` (`Mnemonic`, `CurveUnit`) [12] |
| Top | formation marker | `WellboreMarkerSet.Markers[]` (`MarkerName`, `MarkerMeasuredDepth`) [13] |
| Zone | no direct object | `WellboreIntervalSet.Intervals[]` (`IntervalID`, start/stop measured depth) [14] |
GeoLog collapses well and wellbore into one row [19]. Store the external wellbore ID in a mapping table; do not add a wellbore table in v1. WITSML has `numGovt`/`numAPI` but no UWI [16]; I found no UWI property in the OSDU Wellbore 1.5.1 table [15]. Keep UWI GeoLog-local and map API explicitly. OSDU WellLog 1.5.0 uses `WellboreID`, `Curves[].Mnemonic`, `CurveUnit`, `NullValue`, `SamplingStart/Stop`; `TopMeasuredDepth` is deprecated [12].
## Auth
GeoLog already verifies bearer JWTs with issuer/audience/JWKS and roles; header auth is dev-only [21]. Reuse the caller token where possible, otherwise a service identity. WITSML SOAP endpoints commonly take username/password [18]; store in `secretstore`. ETP uses JWT [5]. OSDU needs bearer + `Data-Partition-Id`, with legal tag and ACL in the record [7][9]. Map OSDU groups to GeoLog roles explicitly and deny unknown groups. Never cache data across partitions without rechecking the legal tag.
## Pull, push, conflict, idempotency, provenance
- **Pull default.** Watermark on external `modifyTime`/version plus payload hash; page and chunk with limits. WITSML growing logs need incremental range queries [4].
- **Push explicit only**, for log runs, tops, zones. Never auto-overwrite the source of record.
- **Conflict (proposal, not a standard):** store base version/hash at last sync. If remote changed and local changed, flag conflict; do not merge. Source-owned fields follow remote, interpretation fields follow local; same-field conflicts require a user decision. Record both sides in audit.
- **Idempotency:** unique `external_ref(system, external_id, entity_type)`; deterministic content hash; same hash = no-op, changed = new revision. GeoLog's LAS upload always inserts a new `LogRun` [20], so the adapter needs its own upsert path. On OSDU update, send the previous version to get optimistic-lock protection [7].
- **Provenance:** `external_ref` (system, external ID, version, hash, legal tag, ACL, last seen) + `sync_run` + GeoLog audit entries [19].
## Adapter boundary
```
backend/integrations/
  contracts.py   # DTOs + Protocol: list_wells, get_wellbore, iter_logs,
                 # get_tops, get_zones, put_log, put_tops
  witsml1411.py  # SOAP client + XML -> DTO
  witsml2.py     # ETP 1.2 client (phase 2)
  osdu.py        # Storage + Wellbore DDMS REST
  mapping.py     # pure DTO <-> model functions
  sync.py        # watermark, idempotency, conflict, audit
```
One migration adds `external_ref` and `sync_run`. No changes to existing domain tables. A new router owns integration endpoints; core services stay unaware of WITSML/OSDU.
## Test strategy without a live server
- **Mapping:** pure-function tests on golden XML/JSON, validated against WITSML XSD and OSDU schemas.
- **Transport:** `httpx.MockTransport`/`responses` for SOAP faults, 401/403, 429/5xx retry, timeouts, partial pages, chunk commit/abandon.
- **Idempotency:** import same fixture twice → one entity, zero new revisions; changed payload → revision plus conflict.
- **Conflict:** local edit plus remote change → conflict recorded, no silent overwrite.
- **Auth/tenancy:** expired token, wrong issuer/audience, missing legal tag, wrong partition, role escalation.
- **Live tests opt-in**, skipped by default, following `tests/test_dlis_lis_real_samples.py` [23]. Test DB isolation already exists [22].
## Non-goals
WITSML 2.0-only support; real-time streaming in v1; becoming an OSDU DDMS; deploying OSDU; syncing projects, annotations, petro params, DST/RFT, completion, production; legal-tag administration; CRS/datum transformation; automatic bidirectional sync; WITSML write-back beyond explicit push.
## Risks
- WITSML dialect variance and `maxDataNodes`/`maxDataPoints` limits [4]; growing-log semantics.
- 1.4.1.1 IDs are only unique within their parent [4]; naive `external_id` collides.
- OSDU schema drift: pin kind versions; 1.5.0 already deprecates fields [12].
- Legal-tag expiry soft-deletes data [9]; partition/ACL leakage is a security incident.
- Bulk curves can exceed memory; stream and cap chunk sizes.
- Recorded fixtures drift from vendor servers; schedule opt-in contract tests.
- Push without a version creates duplicate OSDU versions [7].
## Evidence
| # | Source | URL | Key claim | Type | Confidence |
|---|---|---|---|---|---|
| 1 | Energistics WITSML hub | https://energistics.org/witsml-developers-users | 2.1 current; 2.0 not recommended; ETP 1.2 required for 2.1 | primary | high |
| 2 | WITSML 1.4.4 mapping | http://docs.energistics.opengroup.org/WITSML/WITSML_TOPICS/WITSML-000-015-0-C-sv2000.html | 1.4.1.1→2.0 object changes | primary | high |
| 3 | WITSML 5.3 Log | https://docs.energistics.org/WITSML/WITSML_TOPICS/WITSML-000-050-0-C-sv2000.html | Log/ChannelSet/Channel redesign | primary | high |
| 4 | WITSML STORE API v1.4.1 | https://docs.pronova-tde.com/witsml/v47/pdfs/WITSML_STORE_API_V1.4.1.pdf | SOAP, UID hierarchy, data-object tree | primary | high |
| 5 | CTA 2.3.1 ETP | https://docs.energistics.org/CTA/CTA_TOPICS/CTA-000-021-0-C-sv2100.html | WebSocket, Avro subset, JWT | primary | high |
| 6 | ETP v1.2 publication | https://publications.opengroup.org/standards/energistics-standards/energistics-transfer-protocol/v234 | v1.2 doc v1.2, 2024-07-31 | primary | high |
| 7 | OSDU Storage | https://osdu.pages.opengroup.org/platform/system/storage/ | kind/ACL/legal, versioning, optimistic lock | primary | high |
| 8 | OSDU legal ingestion | https://osdu.pages.opengroup.org/platform/security-and-compliance/legal/ingestion/ | legal tag required before ingest | primary | high |
| 9 | OSDU legal API | https://osdu.pages.opengroup.org/platform/security-and-compliance/legal/api/ | tag properties, expiry, soft delete | primary | high |
| 10 | Wellbore DDMS API | https://osdu.dev1.osdu-cimpl.opengroup.org/api/os-wellbore-ddms/docs | v3 entities, data sessions/chunks | primary | high |
| 11 | OSDU DDMS register | https://osdu.pages.opengroup.org/platform/system/register/HowToBecomeADDMS/ | bulk data + shadow Storage record | primary | high |
| 12 | WellLog 1.5.0 | https://community.opengroup.org/osdu/data/data-definitions/-/raw/master/E-R/work-product-component/WellLog.1.5.0.md | fields; TMD deprecated | primary | high |
| 13 | WellboreMarkerSet 1.5.0 | https://community.opengroup.org/osdu/data/data-definitions/-/raw/master/E-R/work-product-component/WellboreMarkerSet.1.5.0.md | MarkerName, MarkerMeasuredDepth | primary | high |
| 14 | WellboreIntervalSet 1.3.0 | https://community.opengroup.org/osdu/data/data-definitions/-/raw/master/E-R/work-product-component/WellboreIntervalSet.1.3.0.md | IntervalID, start/stop depth | primary | high |
| 15 | Wellbore 1.5.1 | https://community.opengroup.org/osdu/data/data-definitions/-/raw/master/E-R/master-data/Wellbore.1.5.1.md | WellID, FacilityName; no UWI found | primary | medium |
| 16 | WITSML well XSD | https://energistics.org/sites/default/files/schema/WITSML_v1.4.1.1_Data_Schema_with_Raster_v1.0/witsml_v1.4.1.1_data/doc/schema/grp_well.html | well fields; numAPI/numGovt, no UWI | primary | high |
| 17 | WITSML logCurveInfo XSD | https://energistics.org/sites/default/files/schema/WITSML_v1.4.1.1_Data_Schema_with_Raster_v1.0/witsml_v1.4.1.1_data/doc/schema/cs_logCurveInfo.html | curve mnemonic/unit/null | primary | high |
| 18 | Seeq WITSML connector | https://support.seeq.com/latest/cloud/witsml | SOAP username/password, ETP `wss` | secondary | medium |
| 19 | GeoLog models | https://github.com/rinopatrick/geolog/blob/a70be4e/backend/models.py | no external IDs; well/wellbore collapsed | primary | high |
| 20 | GeoLog upload route | https://github.com/rinopatrick/geolog/blob/a70be4e/backend/routers/wells.py | upload always creates new LogRun | primary | high |
| 21 | GeoLog security | https://github.com/rinopatrick/geolog/blob/a70be4e/backend/security.py | JWT/JWKS; header mode dev-only | primary | high |
| 22 | GeoLog conftest | https://github.com/rinopatrick/geolog/blob/a70be4e/tests/conftest.py | per-run test DB | primary | high |
| 23 | GeoLog opt-in real samples | https://github.com/rinopatrick/geolog/blob/a70be4e/tests/test_dlis_lis_real_samples.py | live tests skipped by default | primary | high |
## Coverage status
Checked directly: GeoLog schema, upload path, auth, test setup; Energistics WITSML/ETP pages; OSDU Storage, Legal, DDMS and schema pages. Uncertain: exact WITSML server auth conventions vary by vendor; OSDU Wellbore 1.5.1 UWI absence is based on the property table I searched, not an exhaustive schema audit; WITSML 2.1 JSON schema availability was not verified. No live WITSML or OSDU server was contacted.
## Sources
1. Energistics — WITSML Developers & Users — https://energistics.org/witsml-developers-users
2. Energistics — Data Object Mapping v1.4.1.1 to v2.0 — http://docs.energistics.opengroup.org/WITSML/WITSML_TOPICS/WITSML-000-015-0-C-sv2000.html
3. Energistics — Log Organization — https://docs.energistics.org/WITSML/WITSML_TOPICS/WITSML-000-050-0-C-sv2000.html
4. Energistics — WITSML STORE API v1.4.1 — https://docs.pronova-tde.com/witsml/v47/pdfs/WITSML_STORE_API_V1.4.1.pdf
5. Energistics — CTA 2.3.1 ETP — https://docs.energistics.org/CTA/CTA_TOPICS/CTA-000-021-0-C-sv2100.html
6. Energistics — ETP v1.2 — https://publications.opengroup.org/standards/energistics-standards/energistics-transfer-protocol/v234
7. OSDU — Storage Service — https://osdu.pages.opengroup.org/platform/system/storage/
8. OSDU — Legal ingestion — https://osdu.pages.opengroup.org/platform/security-and-compliance/legal/ingestion/
9. OSDU — Legal API — https://osdu.pages.opengroup.org/platform/security-and-compliance/legal/api/
10. OSDU — Wellbore DDMS API — https://osdu.dev1.osdu-cimpl.opengroup.org/api/os-wellbore-ddms/docs
11. OSDU — How to become a DDMS — https://osdu.pages.opengroup.org/platform/system/register/HowToBecomeADDMS/
12. OSDU — WellLog 1.5.0 — https://community.opengroup.org/osdu/data/data-definitions/-/raw/master/E-R/work-product-component/WellLog.1.5.0.md
13. OSDU — WellboreMarkerSet 1.5.0 — https://community.opengroup.org/osdu/data/data-definitions/-/raw/master/E-R/work-product-component/WellboreMarkerSet.1.5.0.md
14. OSDU — WellboreIntervalSet 1.3.0 — https://community.opengroup.org/osdu/data/data-definitions/-/raw/master/E-R/work-product-component/WellboreIntervalSet.1.3.0.md
15. OSDU — Wellbore 1.5.1 — https://community.opengroup.org/osdu/data/data-definitions/-/raw/master/E-R/master-data/Wellbore.1.5.1.md
16. Energistics — WITSML grp_well XSD — https://energistics.org/sites/default/files/schema/WITSML_v1.4.1.1_Data_Schema_with_Raster_v1.0/witsml_v1.4.1.1_data/doc/schema/grp_well.html
17. Energistics — WITSML cs_logCurveInfo XSD — https://energistics.org/sites/default/files/schema/WITSML_v1.4.1.1_Data_Schema_with_Raster_v1.0/witsml_v1.4.1.1_data/doc/schema/cs_logCurveInfo.html
18. Seeq — WITSML connector — https://support.seeq.com/latest/cloud/witsml
19. GeoLog — models.py — https://github.com/rinopatrick/geolog/blob/a70be4e/backend/models.py
20. GeoLog — routers/wells.py — https://github.com/rinopatrick/geolog/blob/a70be4e/backend/routers/wells.py
21. GeoLog — security.py — https://github.com/rinopatrick/geolog/blob/a70be4e/backend/security.py
22. GeoLog — tests/conftest.py — https://github.com/rinopatrick/geolog/blob/a70be4e/tests/conftest.py
23. GeoLog — tests/test_dlis_lis_real_samples.py — https://github.com/rinopatrick/geolog/blob/a70be4e/tests/test_dlis_lis_real_samples.py
Skipped: no live-server calls, no WITSML 2.1 JSON schema check, no exhaustive OSDU field audit. Risk: vendor WITSML dialects and OSDU kind-version drift may invalidate specific field assumptions.

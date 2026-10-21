# Borehole image ingestion and dip picking — decision report

## Recommendation

Build a **review-first, manual dip picker** on processed image channels, not a vendor-grade image-processing clone.

- **Tier 1 (ship now):** ingest DLIS/LIS image channels with `dlisio`, render azimuth×depth raster, let interpreters drag sinusoids, store picks with quality. No new dependencies.
- **Tier 2 (optional):** automatic sinusoid candidate generation (Hough/gradient search) with confidence scores, always human-reviewed.
- **Validation fixture:** Utah FORGE 78B-32 processed FMI/UBI DLIS, CC-licensed [10]. This gives real orientation channels and pad gaps without vendor licensing.

## Formats and what is actually readable

| Format | Reader | What you get | Limits |
|---|---|---|---|
| FMI/FMI-HD DLIS | `dlisio.dlis` | 192-button microresistivity; 0.2 in resolution; ~80% coverage in 8-in hole; static and dynamic images [1][6] | Processed channels, not raw button voltages; pad gaps |
| OBMI DLIS | `dlisio.dlis` | Oil-based-mud image, 0.4 in features, oriented to borehole geometry [2] | Same channel-level access; different tool response |
| LIS | `dlisio.lis` | DFSR-defined curves; fast channels read separately; duplicate DFSRs return empty arrays [4] | No documented image/multi-dimensional support; verify on a real file |
| Raster PNG/TIFF/PDF | image library | Scanned or plotted image | No standard embedded depth calibration; Petra stores top/base points in a sidecar `.LIC` [9] |
| LAS | existing parser | Scalar curves only | Cannot hold an image |

`dlisio` explicitly supports multi-dimensional channel samples, including “image curves” returned as NumPy arrays [3]. It reads the bytes, not the geology: no pad geometry, speed correction, equalisation, or dip picking. Kirkham’s FMI example shows 360 samples per depth row, static/dynamic channels, and inter-pad gaps requiring interpolation [6]. The FORGE notebook shows the orientation channels that matter: `HAZIM_S` (hole azimuth), `DEVIM_S` (deviation), `P1NO_FBST_S` (pad 1 azimuth), `RB_FBST_S` (relative bearing) [5].

## Minimum orientation and calibration metadata

Required before a pick can be called a true dip:

1. Depth index, direction, and step.
2. Sector count and first-sector azimuth.
3. Orientation reference: true north, magnetic north, or borehole axis.
4. Borehole deviation and hole azimuth (or a survey).
5. Pad/button 1 azimuth and relative bearing.
6. Caliper or hole diameter, for amplitude-to-dip conversion.
7. Magnetic declination, if magnetic-referenced.
8. Null value, gain/offset, and static-vs-dynamic normalisation.

The EPA notes that apparent dip follows from sinusoid amplitude normalised by diameter, and that ignoring magnetic declination, borehole deviation, diameter, and tool decentralisation causes inaccuracies [7]. Without deviation and hole azimuth, only apparent dip exists; EarthScan describes the correction and warns that missing tool/well angle channels leave you with a silently different target [8].

## Image enhancement

Keep raw values immutable and store display parameters. Support static (whole-interval) and dynamic (sliding-window) normalisation [6], gain/offset, histogram equalisation, dead-button patching, and pad-gap interpolation. Linear interpolation is cheap; FFT texture fill is demonstrated by Kirkham [6]; KNN is accurate but slow at well scale [8]. Every rendered image must carry its normalisation settings so a pick can be reproduced.

## Dip-picking data model

`image_asset`: id, well_id, log_run_id, source_format, tool, image_type (static/dynamic), depth_top, depth_bottom, depth_step, depth_direction, n_sectors, first_sector_azimuth, orientation_reference, deviation_curve, hole_azimuth_curve, pad1_azimuth_curve, caliper_curve, null_value, normalization_json, storage_path, checksum.

`dip_pick`: id, asset_id, well_id, depth_md, depth_tvd, dip_deg, azimuth_deg, apparent_dip_deg, apparent_azimuth_deg, feature_type (bedding/fracture/fault/contact/breakout/induced), quality (0–1 or A/B/C), confidence, method (manual/auto/imported), sinusoid_amplitude, sinusoid_phase, fit_rmse, interpreter, notes, created_at, updated_at.

A pick is a fitted sinusoid `y = A·sin(θ + φ) + offset`; offset is depth, amplitude is dip, phase is azimuth [8]. Store the fit parameters alongside the derived orientation so the pick can be redrawn and audited.

## UI and API needs

Canvas: 360° wrap, shared depth ruler with other tracks, pan/zoom, static/dynamic toggle, three-handle sinusoid editing (offset/amplitude/phase), keyboard nudging, snap-to-contrast, quality and feature-type controls, pick table, tadpole and stereonet views, filters, CSV/JSON export.

API: `POST /api/wells/{id}/image-assets` (multipart DLIS/LIS), `GET /api/image-assets/{id}/raster?top=&bottom=&width=&norm=`, `GET|POST|PATCH|DELETE /api/image-assets/{id}/dips`, `POST /api/image-assets/{id}/auto-pick` as a job, `GET /api/wells/{id}/dips.csv`. Reuse the existing job and annotation patterns; add one router, two models, one migration.

## Impossible or unsupported without vendor libraries or licensed data

- Exact reproduction of FMI/OBMI processing: speed correction, button calibration, EMEX, dead-button logic, and vendor gain semantics are undocumented in the file [5][6]. Reimplementation is possible in principle but unvalidated.
- Quantitative fracture aperture from the image alone; it needs shallow resistivity and core/calibration [12].
- 100% circumferential coverage; pads leave real gaps [1][6].
- Encrypted DLIS payloads; `dlisio` documents only limited encrypted-file support [3].
- Enhanced LIS/LIS84: `dlisio` documents LIS79 DFSRs, not LIS84 [4].
- Automatic raster depth calibration from pixels; commercial tools use manual calibration points [9].
- Unoriented images: without deviation/azimuth channels, true dip cannot be recovered [7][8].
- Licensed vendor image data and proprietary tool-response models.

## Risks

- **Memory:** a 360×N float image is large; stream, down-sample for display, store decimated rasters plus raw channel references.
- **Silent apparent/true mix-up:** store the reference frame on every pick and display it.
- **LIS duplicated DFSRs:** `dlisio` returns empty arrays, so validate row counts [4].
- **Depth registration drift** between image and conventional curves; require top/base checks.
- **Auto-pick credibility:** sinusoidal fitting is sensitive to pad gaps and bedding contrast; keep confidence and human review.
- **Scope creep:** vendor-grade image conditioning is a product in itself; resist it.

## Coverage Status

Directly checked: SLB FMI/OBMI pages, `dlisio` DLIS/LIS docs, Kirkham FMI workflow, ICWallis FORGE notebook, EPA OTV guidance, EarthScan primer, IHS Petra raster calibration, FORGE dataset listing. Not checked: actual FORGE ZIP contents, LIS image files, and `dlisio` behaviour on encrypted or malformed files. No repository files changed.

## Sources

1. SLB, FMI Fullbore Formation Microimager — https://www.slb.com/products-and-services/innovating-in-oil-and-gas/reservoir-characterization/surface-and-downhole-logging/wireline-openhole-logging/fmi-fullbore-formation-microimager
2. SLB, OBMI Oil-Based Microimager — https://www.slb.com/products-and-services/innovating-in-oil-and-gas/reservoir-characterization/surface-and-downhole-logging/wireline-openhole-logging/obmi-oil-based-microimager
3. dlisio, DLIS Curves and API Reference — https://dlisio.readthedocs.io/en/stable/dlis/curves.html ; https://dlisio.readthedocs.io/en/latest/dlis/api.html
4. dlisio, LIS User Guide and API Reference — https://dlisio.readthedocs.io/en/latest/lis/userguide.html ; https://dlisio.readthedocs.io/en/latest/lis/api.html
5. I. Wallis, borehole-image-analysis-with-python, DLIS notebook — https://github.com/ICWallis/borehole-image-analysis-with-python/blob/main/7_DLIS_files.ipynb
6. P. Kirkham, Import and Process FMI DLIS Using dlisio — https://pkirkham.github.io/analysis/dlisio-fmi-interpolation/
7. US EPA, Borehole Optical Televiewer — https://19january2025snapshot.epa.gov/environmental-geophysics/borehole-optical-televiewer-otv
8. EarthScan, Borehole Image Logs 101 — https://www.earthscan.io/insights/fmi-image-logs-101-sinusoids-dip-azimuth
9. IHS Petra, Raster Image Calibration — https://onlinehelp.ihs.com/Energy/Petra/2019/Content/main_rasterimagecalibration.htm
10. OEDI, Utah FORGE Well 78B-32 FMI and UBI Processed Data — https://data.openei.org/submissions/9787
11. J. Kherroubi, A contrario dip picking for borehole imaging — https://pubs.geoscienceworld.org/seg/geophysics/article/86/4/V339/606153/A-contrario-dip-picking-for-borehole-imagingA
12. US12332157B2, Methods and systems for determining reservoir and fracture properties — https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12332157
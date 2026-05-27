"""Zonation + Net Pay Report router for GeoLog."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import numpy as np
import io
import csv
import json
import math
import datetime

try:
    from database import get_db
    from models import Well, LogRun, CurveData, FormationTop, Zone, PetroParams
except ImportError:
    from backend.database import get_db
    from backend.models import Well, LogRun, CurveData, FormationTop, Zone, PetroParams

router = APIRouter(prefix="/api/wells/{wid}", tags=["zonation"])


def _get_latest_run(wid: int, db: Session):
    return db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()


def _extract_curve(db, lr_id, mnemonics):
    """Try mnemonics in order, return (array, mnemonic) or (None, None)."""
    if isinstance(mnemonics, str):
        mnemonics = [mnemonics]
    for mn in mnemonics:
        cd = db.query(CurveData).filter(
            CurveData.log_run_id == lr_id, CurveData.mnemonic == mn
        ).first()
        if cd and cd.data_binary:
            arr = np.frombuffer(cd.data_binary, dtype=np.float32).copy()
            if len(arr) > 0:
                return arr, mn
    return None, None


def _sanitize(v):
    """Convert numpy/NaN to JSON-safe value."""
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        fv = float(v)
        return None if (math.isnan(fv) or math.isinf(fv)) else fv
    if isinstance(v, (np.integer, int)):
        return int(v)
    return v


def _find_pay_intervals(pay_mask, depth, gap_merge_ft=2.0):
    """Find contiguous True runs in pay_mask, merge within gap tolerance."""
    if len(pay_mask) == 0:
        return []
    intervals = []
    in_zone = False
    start_idx = 0
    for i, val in enumerate(pay_mask):
        if val and not in_zone:
            in_zone = True
            start_idx = i
        elif not val and in_zone:
            in_zone = False
            intervals.append((start_idx, i - 1))
    if in_zone:
        intervals.append((start_idx, len(pay_mask) - 1))

    # Merge intervals within gap_merge_ft
    if not intervals or gap_merge_ft <= 0:
        return intervals
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        prev_s, prev_e = merged[-1]
        gap = depth[s] - depth[prev_e]
        if gap <= gap_merge_ft:
            merged[-1] = (prev_s, e)
        else:
            merged.append((s, e))
    return merged


def _compute_zone_stats(intervals, depth, vsh, phie, sw, step):
    """Compute per-zone statistics."""
    zones = []
    for i, (s, e) in enumerate(intervals):
        top = float(depth[s])
        base = float(depth[e])
        gross = abs(base - top)
        npts = e - s + 1

        vsh_slice = vsh[s:e+1] if vsh is not None else None
        phie_slice = phie[s:e+1] if phie is not None else None
        sw_slice = sw[s:e+1] if sw is not None else None

        # Count pay samples within zone (for net pay)
        if vsh_slice is not None and phie_slice is not None and sw_slice is not None:
            valid_mask = (
                ~np.isnan(vsh_slice) & ~np.isnan(phie_slice) & ~np.isnan(sw_slice)
            )
            pay_in_zone = np.sum(valid_mask)
            net_pay = pay_in_zone * step
        else:
            pay_in_zone = npts
            net_pay = gross

        ntg = gross / net_pay if net_pay > 0 else 0.0
        if ntg > 1:
            ntg = 1.0 / ntg  # normalize if inverted

        def _avg(arr_slice):
            if arr_slice is None:
                return None
            valid = arr_slice[~np.isnan(arr_slice)]
            return float(np.mean(valid)) if len(valid) > 0 else None

        zones.append({
            "name": f"Zone_{i+1}",
            "top_depth": _sanitize(top),
            "bottom_depth": _sanitize(base),
            "gross_ft": _sanitize(gross),
            "net_pay_ft": _sanitize(net_pay),
            "ntg": _sanitize(ntg),
            "avg_phie": _avg(phie_slice),
            "avg_sw": _avg(sw_slice),
            "avg_vsh": _avg(vsh_slice),
            "num_points": npts,
        })
    return zones


@router.post("/auto-zone")
def auto_zone(wid: int, data: dict, db: Session = Depends(get_db)):
    """Auto-generate zones from petrophysical cutoffs."""
    lr = _get_latest_run(wid, db)
    if not lr:
        raise HTTPException(404, "No log run found for well")
    if not lr.num_points or lr.num_points < 2:
        raise HTTPException(400, "Log run has insufficient data")

    depth = np.linspace(lr.start_depth, lr.stop_depth, lr.num_points)
    step = abs(float(depth[1] - depth[0])) if len(depth) > 1 else 1.0

    # Cutoffs from request or saved PetroParams
    vsh_max = float(data.get("vsh_max", 0.35))
    phie_min = float(data.get("phie_min", 0.10))
    sw_max = float(data.get("sw_max", 0.60))
    gap_merge_ft = float(data.get("gap_merge_ft", 2.0))

    # Extract curves with fallback chains
    vsh_arr, vsh_mn = _extract_curve(db, lr.id, ["VSH", "VCL", "VSH_GR", "VSH_LARIONOV"])
    phie_arr, phie_mn = _extract_curve(db, lr.id, ["PHIE", "PHID", "PHI_E"])
    sw_arr, sw_mn = _extract_curve(db, lr.id, ["SW", "SWE"])

    # Fallback: compute PHIE from RHOB if missing
    if phie_arr is None:
        rhob_arr, _ = _extract_curve(db, lr.id, ["RHOB", "ZDEN", "DEN"])
        if rhob_arr is not None:
            phie_arr = np.clip((2.65 - rhob_arr) / (2.65 - 1.0), 0, 1)
            phie_mn = "PHIE_from_RHOB"

    # Fallback: compute SW from Archie if missing
    if sw_arr is None and phie_arr is not None:
        rt_arr, _ = _extract_curve(db, lr.id, ["RT", "RILD", "RILM", "RMED", "RES"])
        if rt_arr is not None:
            params = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
            a = params.a if params else 1.0
            m = params.m if params else 2.0
            n = params.n if params else 2.0
            rw = params.rw if params else 0.1
            with np.errstate(divide='ignore', invalid='ignore'):
                sw_arr = np.clip(
                    (a * rw / (phie_arr ** m * rt_arr + 1e-10)) ** (1.0 / n), 0, 1
                )
            sw_mn = "SW_from_Archie"

    if vsh_arr is None:
        raise HTTPException(400, "No VSH/VCL curve found — cannot compute zones")
    if phie_arr is None:
        raise HTTPException(400, "No PHIE/PHID/RHOB curve found — cannot compute zones")
    if sw_arr is None:
        raise HTTPException(400, "No SW/RT curve found — cannot compute zones")

    # Build pay mask
    pay_mask = (
        (vsh_arr < vsh_max) &
        (phie_arr > phie_min) &
        (sw_arr < sw_max) &
        ~np.isnan(vsh_arr) &
        ~np.isnan(phie_arr) &
        ~np.isnan(sw_arr)
    )

    intervals = _find_pay_intervals(pay_mask, depth, gap_merge_ft)
    zones = _compute_zone_stats(intervals, depth, vsh_arr, phie_arr, sw_arr, step)

    # Overall summary
    total_gross = sum(z["gross_ft"] for z in zones)
    total_net = sum(z["net_pay_ft"] for z in zones)
    overall_ntg = total_gross / total_net if total_net > 0 else 0

    # Weighted averages
    def _wavg(zones, key, weight_key="net_pay_ft"):
        vals = [(z[key], z[weight_key]) for z in zones if z[key] is not None and z[weight_key] and z[weight_key] > 0]
        if not vals:
            return None
        total_w = sum(w for _, w in vals)
        return sum(v * w for v, w in vals) / total_w if total_w > 0 else None

    return {
        "well_id": wid,
        "cutoffs": {"vsh_max": vsh_max, "phie_min": phie_min, "sw_max": sw_max, "gap_merge_ft": gap_merge_ft},
        "curves_used": {"vsh": vsh_mn, "phie": phie_mn, "sw": sw_mn},
        "zones": zones,
        "summary": {
            "num_zones": len(zones),
            "total_gross_ft": _sanitize(total_gross),
            "total_net_pay_ft": _sanitize(total_net),
            "overall_ntg": _sanitize(overall_ntg),
            "avg_phie": _wavg(zones, "avg_phie"),
            "avg_sw": _wavg(zones, "avg_sw"),
            "avg_vsh": _wavg(zones, "avg_vsh"),
        },
    }


@router.post("/auto-zone-from-tops")
def auto_zone_from_tops(wid: int, db: Session = Depends(get_db)):
    """Auto-create zones from pairs of formation tops (top[i] → top[i+1])."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    tops = (
        db.query(FormationTop)
        .filter(FormationTop.well_id == wid)
        .order_by(FormationTop.depth.asc())
        .all()
    )
    if len(tops) < 2:
        # Auto-pick tops from GR curve if no manual tops
        lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
        if lr:
            gr_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == "GR").first()
            depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
            if gr_cd and depth_cd:
                gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy()
                depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()
                # Find significant peaks/valleys in GR
                from scipy.signal import find_peaks
                # Smooth GR for robust peak detection
                kernel = np.ones(21) / 21
                gr_smooth = np.convolve(gr, kernel, mode='same')
                # Find peaks (sand tops = low GR)
                valleys, _ = find_peaks(-gr_smooth, prominence=np.nanstd(gr) * 0.5, distance=100)
                if len(valleys) >= 2:
                    for vi, v in enumerate(valleys[:10]):
                        ft = FormationTop(
                            well_id=wid,
                            formation_name=f"Auto_Top_{vi+1}",
                            depth=float(depth[v]),
                            depth_unit="FT",
                            color=f"#{hash(str(vi)) % 0xFFFFFF:06x}",
                        )
                        db.add(ft)
                    db.commit()
                    tops = (
                        db.query(FormationTop)
                        .filter(FormationTop.well_id == wid)
                        .order_by(FormationTop.depth.asc())
                        .all()
                    )
    if len(tops) < 2:
        raise HTTPException(400, "Need at least 2 formation tops to create zones (could not auto-detect from GR)")

    # Delete existing zones for this well
    db.query(Zone).filter(Zone.well_id == wid).delete()

    colors = ['#1f6feb', '#238636', '#9e6a03', '#8957e5', '#da3633',
              '#f78166', '#3fb950', '#58a6ff', '#d29922', '#f0883e']

    created = []
    for i in range(len(tops) - 1):
        t = tops[i]
        t_next = tops[i + 1]
        zone_name = f"{t.formation_name} — {t_next.formation_name}"
        z = Zone(
            well_id=wid,
            name=zone_name,
            top_depth=float(t.depth),
            bottom_depth=float(t_next.depth),
            color=colors[i % len(colors)],
            sort_order=i,
        )
        db.add(z)
        created.append(zone_name)

    db.commit()
    return {"status": "ok", "zones_created": len(created), "zone_names": created}



@router.get("/zone-report")
def zone_report(wid: int, db: Session = Depends(get_db)):
    """Get saved zone report for a well."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    zones = db.query(Zone).filter(Zone.well_id == wid).order_by(Zone.sort_order, Zone.top_depth).all()
    zone_list = []
    total_gross = 0
    total_net = 0
    for z in zones:
        gross = abs(z.bottom_depth - z.top_depth)
        total_gross += gross
        zone_list.append({
            "id": z.id,
            "name": z.name,
            "top_depth": _sanitize(z.top_depth),
            "bottom_depth": _sanitize(z.bottom_depth),
            "color": z.color,
            "gross_ft": _sanitize(gross),
        })

    return {
        "well_id": wid,
        "well_name": well.name,
        "zones": zone_list,
        "summary": {
            "num_zones": len(zone_list),
            "total_gross_ft": _sanitize(total_gross),
        },
    }


@router.get("/zone-report/csv")
def zone_report_csv(wid: int, db: Session = Depends(get_db)):
    """Export zone report as CSV."""
    zones = db.query(Zone).filter(Zone.well_id == wid).order_by(Zone.sort_order, Zone.top_depth).all()
    well = db.query(Well).filter(Well.id == wid).first()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Well", well.name if well else f"Well_{wid}", "", ""])
    writer.writerow(["UWI", well.uwi if well else "", "", ""])
    writer.writerow([])
    writer.writerow(["Zone", "Top Depth", "Base Depth", "Gross (ft)"])
    total_gross = 0
    for z in zones:
        gross = abs(z.bottom_depth - z.top_depth)
        total_gross += gross
        writer.writerow([z.name, f"{z.top_depth:.1f}", f"{z.bottom_depth:.1f}", f"{gross:.1f}"])
    writer.writerow([])
    writer.writerow(["TOTAL", "", "", f"{total_gross:.1f}"])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=zone_report_well_{wid}.csv"},
    )


@router.get("/zone-report/pdf")
def zone_report_pdf(wid: int, db: Session = Depends(get_db)):
    """Export zone report as PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    well = db.query(Well).filter(Well.id == wid).first()
    zones = db.query(Zone).filter(Zone.well_id == wid).order_by(Zone.sort_order, Zone.top_depth).all()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    elements = []

    # Header
    elements.append(Paragraph(f"Zone Report — {well.name if well else f'Well {wid}'}", styles["Title"]))
    if well and well.uwi:
        elements.append(Paragraph(f"UWI: {well.uwi}", styles["Normal"]))
    elements.append(Paragraph(f"Generated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]))
    elements.append(Spacer(1, 10*mm))

    # Zone table
    header = ["Zone", "Top Depth", "Base Depth", "Gross (ft)"]
    rows = [header]
    total_gross = 0
    for z in zones:
        gross = abs(z.bottom_depth - z.top_depth)
        total_gross += gross
        rows.append([z.name, f"{z.top_depth:.1f}", f"{z.bottom_depth:.1f}", f"{gross:.1f}"])
    rows.append(["TOTAL", "", "", f"{total_gross:.1f}"])

    table = Table(rows, colWidths=[40*mm, 35*mm, 35*mm, 30*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f6feb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f6f8fa")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e6edf3")),
        ("FONTSIZE", (0, -1), (-1, -1), 10),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 8*mm))

    # Summary
    elements.append(Paragraph(f"Total Zones: {len(zones)}", styles["Heading3"]))
    elements.append(Paragraph(f"Total Gross Interval: {total_gross:.1f} ft", styles["Normal"]))

    doc.build(elements)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=zone_report_well_{wid}.pdf"},
    )

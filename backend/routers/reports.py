from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

try:
    from database import get_db
    from models import Well, FormationTop, LogRun, CurveData, PetroParams
except ImportError:
    from backend.database import get_db
    from backend.models import Well, FormationTop, LogRun, CurveData, PetroParams

import datetime
import io
import numpy as np

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics import renderPDF
from starlette.responses import StreamingResponse

router = APIRouter(prefix="/api/wells/{wid}", tags=["reports"])


@router.get("/report-pdf")
def generate_petrophysical_report_pdf(
    wid: int,
    db: Session = Depends(get_db),
    template: str = Query(default="professional"),
    include_curve_summary: bool = Query(default=True),
    include_qc: bool = Query(default=True),
):
    """Generate professional petrophysical report as PDF."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    tops = (
        db.query(FormationTop)
        .filter(FormationTop.well_id == wid)
        .order_by(FormationTop.depth.asc(), FormationTop.id.asc())
        .all()
    )
    try:
        from main import zone_stats
    except ImportError:
        from backend.main import zone_stats
    zones_resp = zone_stats(wid, db)
    zones = zones_resp.get("zones", [])
    cutoffs = zones_resp.get("cutoffs", {})

    runs = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.run_number.asc()).all()
    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()

    def _fmt(val, nd=2):
        if val is None:
            return "-"
        try:
            return f"{float(val):.{nd}f}"
        except Exception:
            return str(val)

    def _safe_text(v, default="-"):
        return str(v) if v not in (None, "") else default

    # Build PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"{well.name or 'Well'} Petrophysical Report",
        author="GeoLog",
    )

    styles = getSampleStyleSheet()
    template_key = (template or "professional").strip().lower()
    palette = {
        "professional": {"title": "#1f2937", "head_bg": "#e5e7eb", "section_bg": "#f3f4f6"},
        "executive": {"title": "#0f172a", "head_bg": "#dbeafe", "section_bg": "#eff6ff"},
        "compact": {"title": "#111827", "head_bg": "#e5e7eb", "section_bg": "#f9fafb"},
    }.get(template_key, {"title": "#1f2937", "head_bg": "#e5e7eb", "section_bg": "#f3f4f6"})

    section_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=colors.HexColor(palette["title"]),
        spaceBefore=8,
        spaceAfter=4,
    )
    body_style = ParagraphStyle("BodySmall", parent=styles["Normal"], fontSize=9, leading=11)

    elements = []

    # 1) Header
    report_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    header_tbl = Table([
        [
            Paragraph("<b>COMPANY LOGO</b><br/><font size='8'>[Placeholder]</font>", body_style),
            Paragraph(
                f"<b>{_safe_text(well.operator, 'GeoLog')}</b><br/>"
                f"<font size='14'><b>Petrophysical Report</b></font><br/>"
                f"Date: {report_date}<br/>"
                f"Well: <b>{_safe_text(well.name)}</b>",
                body_style,
            ),
        ]
    ], colWidths=[45 * mm, 130 * mm])
    header_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#9ca3af")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f3f4f6")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.extend([header_tbl, Spacer(1, 6)])

    # 2) Well Information
    elements.append(Paragraph("2. Well Information", section_style))
    location_text = "-"
    if well.latitude is not None and well.longitude is not None:
        location_text = f"{_fmt(well.latitude, 5)}, {_fmt(well.longitude, 5)}"
    country = _safe_text(well.project.country if well.project else None)
    well_info = [
        ["UWI", _safe_text(well.uwi), "Field", _safe_text(well.field_name)],
        ["Operator", _safe_text(well.operator), "Country", country],
        ["Location (Lat, Lon)", location_text, "KB Elevation", _fmt(well.elevation, 2)],
    ]
    wt = Table(well_info, colWidths=[36 * mm, 52 * mm, 34 * mm, 53 * mm])
    wt.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9ca3af")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f9fafb")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f9fafb")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.extend([wt, Spacer(1, 6)])

    # 3) Log Run Summary
    elements.append(Paragraph("3. Log Run Summary", section_style))
    log_data = [["Run", "Depth Range", "Curves", "Step"]]
    if runs:
        for lr in runs:
            cds = db.query(CurveData.mnemonic).filter(CurveData.log_run_id == lr.id).all()
            curve_names = ", ".join(sorted({c[0] for c in cds if c and c[0]})) or "-"
            log_data.append([
                str(lr.run_number),
                f"{_fmt(lr.start_depth, 1)} - {_fmt(lr.stop_depth, 1)}",
                curve_names,
                _fmt(lr.step, 3),
            ])
    else:
        log_data.append(["-", "-", "-", "-"])
    lrt = Table(log_data, colWidths=[16 * mm, 36 * mm, 106 * mm, 17 * mm])
    lrt.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9ca3af")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(palette["head_bg"])),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.extend([lrt, Spacer(1, 6)])

    # 4) Formation Tops
    elements.append(Paragraph("4. Formation Tops", section_style))
    tops_data = [["Formation", "Depth", "Quality"]]
    if tops:
        for t in tops:
            quality = _safe_text(t.notes, "N/A")
            tops_data.append([_safe_text(t.formation_name), _fmt(t.depth, 2), quality])
    else:
        tops_data.append(["-", "-", "-"])
    tt = Table(tops_data, colWidths=[72 * mm, 25 * mm, 78 * mm])
    tt.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9ca3af")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(palette["head_bg"])),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.extend([tt, Spacer(1, 6)])

    # 5) Petrophysical Summary per zone
    elements.append(Paragraph("5. Petrophysical Summary", section_style))
    zs_data = [["Zone", "Gross", "Net", "NTG", "Avg PHIE", "Avg SW", "Avg VSH"]]
    if zones:
        for z in zones:
            zs_data.append([
                _safe_text(z.get("name")),
                _fmt(z.get("gross_ft"), 2),
                _fmt(z.get("net_pay_ft"), 2),
                _fmt(z.get("ntg"), 3),
                _fmt(z.get("avg_phie"), 4),
                _fmt(z.get("avg_sw"), 4),
                _fmt(z.get("avg_vsh"), 4),
            ])
    else:
        zs_data.append(["-", "-", "-", "-", "-", "-", "-"])
    zst = Table(zs_data, colWidths=[54 * mm, 18 * mm, 18 * mm, 16 * mm, 22 * mm, 22 * mm, 22 * mm])
    zst.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9ca3af")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(palette["head_bg"])),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.extend([zst, Spacer(1, 6)])

    # 5b) Embedded Plot (Net Pay by Zone)
    if zones:
        elements.append(Paragraph("5b. Net Pay Plot", section_style))
        labels = [str(z.get("name", f"Z{i+1}"))[:10] for i, z in enumerate(zones[:12])]
        vals = [float(z.get("net_pay_ft") or 0.0) for z in zones[:12]]
        draw = Drawing(165 * mm, 48 * mm)
        chart = VerticalBarChart()
        chart.x = 10
        chart.y = 12
        chart.height = 34 * mm
        chart.width = 145 * mm
        chart.data = [vals]
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max(vals) * 1.15 if max(vals) > 0 else 1
        chart.valueAxis.valueStep = max(chart.valueAxis.valueMax / 5.0, 0.2)
        chart.categoryAxis.categoryNames = labels
        chart.categoryAxis.labels.boxAnchor = 'ne'
        chart.categoryAxis.labels.angle = 25
        chart.categoryAxis.labels.fontSize = 7
        chart.bars[0].fillColor = colors.HexColor("#4f46e5")
        chart.bars[0].strokeColor = colors.HexColor("#312e81")
        draw.add(chart)
        elements.append(draw)
        elements.append(Spacer(1, 6))

    # 6) Parameters used
    elements.append(Paragraph("6. Parameters Used", section_style))
    rw = pp.rw if pp and pp.rw is not None else 0.10
    m = pp.m if pp and pp.m is not None else 2.0
    n = pp.n if pp and pp.n is not None else 2.0
    params_data = [
        ["Rw", _fmt(rw, 4), "m", _fmt(m, 3), "n", _fmt(n, 3)],
        ["VCL cutoff", _fmt(cutoffs.get("vsh", 0.35), 3),
         "PHIE cutoff", _fmt(cutoffs.get("phie", 0.10), 3),
         "SW cutoff", _fmt(cutoffs.get("sw", 0.60), 3)],
    ]
    pt = Table(params_data, colWidths=[30 * mm, 24 * mm, 14 * mm, 24 * mm, 14 * mm, 24 * mm])
    pt.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9ca3af")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f9fafb")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f9fafb")),
        ("BACKGROUND", (4, 0), (4, -1), colors.HexColor("#f9fafb")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ]))
    elements.append(pt)
    elements.append(Spacer(1, 6))

    # 7) Curve Summary (optional)
    if include_curve_summary and runs:
        elements.append(Paragraph("7. Curve Statistical Summary", section_style))
        run = runs[-1]
        cds = db.query(CurveData).filter(CurveData.log_run_id == run.id).all()
        cs_data = [["Curve", "Min", "Max", "Mean"]]
        for cd in cds[:18]:
            arr = np.frombuffer(cd.data_binary, dtype=np.float64)
            v = arr[np.isfinite(arr)]
            if len(v) == 0:
                cs_data.append([cd.mnemonic, "-", "-", "-"])
            else:
                cs_data.append([cd.mnemonic, _fmt(np.min(v), 3), _fmt(np.max(v), 3), _fmt(np.mean(v), 3)])
        cst = Table(cs_data, colWidths=[36 * mm, 44 * mm, 44 * mm, 44 * mm])
        cst.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9ca3af")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(palette["head_bg"])),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        elements.extend([cst, Spacer(1, 6)])

    # 8) QC Snapshot (optional)
    if include_qc:
        elements.append(Paragraph("8. QC Snapshot", section_style))
        qc_rows = [["Metric", "Value"]]
        try:
            qc = run_qc_autofix(wid, db)
            qc_rows.extend([
                ["QC Score", str(qc.get("score", "-"))],
                ["Grade", str(qc.get("grade", "-"))],
                ["Critical Issues", str(qc.get("critical", 0))],
                ["Warnings", str(qc.get("warnings", 0))],
                ["Total Curves", str(qc.get("total_curves", 0))],
            ])
        except Exception:
            qc_rows.append(["Status", "QC data unavailable"])
        qct = Table(qc_rows, colWidths=[56 * mm, 112 * mm])
        qct.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9ca3af")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(palette["head_bg"])),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ]))
        elements.extend([qct, Spacer(1, 6)])

    # 9) Footer
    def _draw_footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawString(16 * mm, 10 * mm, "Generated by GeoLog")
        canvas.drawRightString(194 * mm, 10 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    buffer.seek(0)

    safe_name = (well.name or "well").replace("/", "_").replace("\\", "_").replace(" ", "_")
    fname = f"{safe_name}_petrophysical_report.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{fname}"'}
    return StreamingResponse(buffer, media_type="application/pdf", headers=headers)



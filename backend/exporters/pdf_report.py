import io
import base64
import os
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas as pdfcanvas

from backend.models import AnalysisResult, Severity

ECLYPSE_BLUE = colors.HexColor("#0057FF")
ECLYPSE_DARK = colors.HexColor("#0A0A0A")
ECLYPSE_LIGHT = colors.HexColor("#F5F7FA")
COLOR_CRITICAL = colors.HexColor("#FF3B3B")
COLOR_WARNING = colors.HexColor("#FFAA00")
COLOR_INFO = colors.HexColor("#00B4D8")
COLOR_OK = colors.HexColor("#22C55E")

W, H = A4


class NumberedCanvas(pdfcanvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(num_pages)
            super().showPage()
        super().save()

    def _draw_footer(self, total):
        self.saveState()
        self.setFillColor(colors.HexColor("#888888"))
        self.setFont("Helvetica", 8)
        page_num = self._pageNumber
        self.drawRightString(W - 20 * mm, 10 * mm, f"Página {page_num} de {total}")
        self.drawString(20 * mm, 10 * mm, "Eclypse Web Intelligence · eclypsedesign.com")
        self.restoreState()


def _score_color(score: int) -> colors.Color:
    if score >= 70:
        return COLOR_CRITICAL
    if score >= 40:
        return COLOR_WARNING
    return COLOR_OK


def _severity_color(sev: Severity) -> colors.Color:
    return {Severity.critical: COLOR_CRITICAL, Severity.warning: COLOR_WARNING, Severity.info: COLOR_INFO}[sev]


def _severity_label(sev: Severity) -> str:
    return {Severity.critical: "CRÍTICO", Severity.warning: "ATENCIÓN", Severity.info: "INFO"}[sev]


def generate(result: AnalysisResult, output_dir: str = "./pdfs") -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filename = f"{result.job_id}.pdf"
    filepath = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    normal = styles["Normal"]

    def style(name="Normal", **kwargs):
        return ParagraphStyle(name, parent=styles[name], **kwargs)

    title_style = style("h1_custom", fontSize=22, textColor=ECLYPSE_DARK, spaceAfter=4, fontName="Helvetica-Bold")
    subtitle_style = style("subtitle", fontSize=11, textColor=colors.HexColor("#555555"), spaceAfter=12)
    section_style = style("section", fontSize=13, textColor=ECLYPSE_BLUE, spaceAfter=6, spaceBefore=14, fontName="Helvetica-Bold")
    body_style = style("body", fontSize=9, textColor=ECLYPSE_DARK, spaceAfter=4)
    small_style = style("small", fontSize=8, textColor=colors.HexColor("#666666"))
    bold_style = style("bold", fontSize=9, textColor=ECLYPSE_DARK, fontName="Helvetica-Bold")
    center_style = style("center", fontSize=9, alignment=TA_CENTER)

    story = []

    # ── COVER ──────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph("ECLYPSE", style("cover_brand", fontSize=10, textColor=ECLYPSE_BLUE, fontName="Helvetica-Bold", spaceAfter=2)))
    story.append(Paragraph("Web Intelligence Analyzer", style("cover_title", fontSize=26, textColor=ECLYPSE_DARK, fontName="Helvetica-Bold", spaceAfter=4)))
    story.append(HRFlowable(width="100%", thickness=2, color=ECLYPSE_BLUE, spaceAfter=10))
    story.append(Paragraph(f"Análisis de: <b>{result.domain}</b>", subtitle_style))
    story.append(Paragraph(f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", small_style))
    if result.name:
        story.append(Paragraph(f"Preparado para: {result.name}", small_style))
    story.append(Spacer(1, 8 * mm))

    # Score pill
    score_val = result.score.total if result.score else 0
    label = result.score.label if result.score else ""
    score_color = _score_color(score_val)

    score_table = Table(
        [[Paragraph(f"<b>{score_val}/100</b>", style("sc", fontSize=32, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_CENTER)),
          Paragraph(f"<b>{label}</b>", style("lb", fontSize=14, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_CENTER))]],
        colWidths=[50 * mm, 100 * mm], rowHeights=[22 * mm]
    )
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), score_color),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 6 * mm))

    # Score breakdown table
    if result.score and result.score.breakdown:
        bd_data = [["Módulo", "Puntos"]] + [[k, str(v)] for k, v in result.score.breakdown.items()]
        bd_table = Table(bd_data, colWidths=[80 * mm, 30 * mm])
        bd_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ECLYPSE_DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [ECLYPSE_LIGHT, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDDD")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(bd_table)
        story.append(Spacer(1, 8 * mm))

    # ── TOP ISSUES ─────────────────────────────────────────────────────────────
    if result.score and result.score.top_issues:
        story.append(Paragraph("Principales problemas detectados", section_style))
        for issue in result.score.top_issues:
            sev_color = _severity_color(issue.severity)
            sev_label = _severity_label(issue.severity)
            row = [[
                Paragraph(f"<font color='#{sev_color.hexval()[1:] if hasattr(sev_color, 'hexval') else 'FF0000'}'><b>{sev_label}</b></font>", body_style),
                Paragraph(f"<b>{issue.message}</b>", body_style),
                Paragraph(issue.detail or "", small_style)
            ]]
            t = Table(row, colWidths=[22 * mm, 70 * mm, 68 * mm])
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#EEEEEE")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(t)
        story.append(Spacer(1, 6 * mm))

    # ── CMS ────────────────────────────────────────────────────────────────────
    if result.cms:
        story.append(HRFlowable(width="100%", thickness=1, color=ECLYPSE_BLUE, spaceAfter=4))
        story.append(Paragraph("CMS y Tecnología", section_style))
        cms = result.cms
        rows = [["Campo", "Valor"]]
        rows.append(["CMS detectado", cms.cms or "Desconocido"])
        if cms.version:
            rows.append(["Versión", cms.version])
        if cms.theme:
            rows.append(["Tema activo", cms.theme])
        rows.append(["Plugins detectados", str(len(cms.plugins))])
        _add_info_table(story, rows)

    # ── SECURITY ───────────────────────────────────────────────────────────────
    if result.security:
        story.append(Paragraph("Seguridad", section_style))
        sec = result.security
        rows = [["Campo", "Valor"]]
        rows.append(["SSL válido", "✓ Sí" if sec.ssl_valid else "✗ No"])
        if sec.ssl_issuer:
            rows.append(["Emisor SSL", sec.ssl_issuer])
        if sec.ssl_days_left is not None:
            rows.append(["Días para vencer", str(sec.ssl_days_left)])
        missing_h = [h for h, v in sec.headers.items() if v is None]
        rows.append(["Headers faltantes", ", ".join(missing_h) if missing_h else "Ninguno"])
        if sec.exposed_files:
            rows.append(["Archivos expuestos", ", ".join(sec.exposed_files)])
        _add_info_table(story, rows)

    # ── PERFORMANCE ────────────────────────────────────────────────────────────
    if result.performance:
        story.append(Paragraph("Performance", section_style))
        perf = result.performance
        rows = [["Métrica", "Valor"]]
        if perf.mobile_score is not None:
            rows.append(["Score mobile", f"{perf.mobile_score}/100"])
        if perf.desktop_score is not None:
            rows.append(["Score desktop", f"{perf.desktop_score}/100"])
        if perf.lcp:
            rows.append(["LCP", f"{perf.lcp}s"])
        if perf.fcp:
            rows.append(["FCP", f"{perf.fcp}s"])
        if perf.cls:
            rows.append(["CLS", str(perf.cls)])
        if perf.ttfb:
            rows.append(["TTFB", f"{perf.ttfb}s"])
        rows.append(["CDN", f"✓ {perf.cdn_provider}" if perf.uses_cdn else "✗ No usa CDN"])
        _add_info_table(story, rows)

        if perf.screenshot_mobile:
            try:
                story.append(Paragraph("Vista mobile del sitio", bold_style))
                img_data = perf.screenshot_mobile
                if img_data.startswith("data:"):
                    img_data = img_data.split(",", 1)[1]
                img_bytes = base64.b64decode(img_data)
                from reportlab.platypus import Image as RLImage
                img_stream = io.BytesIO(img_bytes)
                img = RLImage(img_stream, width=60 * mm, height=100 * mm)
                story.append(img)
                story.append(Spacer(1, 4 * mm))
            except Exception:
                pass

    # ── SEO ────────────────────────────────────────────────────────────────────
    if result.seo:
        story.append(Paragraph("SEO", section_style))
        seo = result.seo
        checks = [
            ("Meta title", seo.has_meta_title, seo.meta_title),
            ("Meta description", seo.has_meta_description, None),
            ("robots.txt", seo.has_robots_txt, None),
            ("sitemap.xml", seo.has_sitemap, None),
            ("H1 tag", seo.h1_count == 1, f"{seo.h1_count} encontrado(s)"),
            ("Alt text en imágenes", seo.images_total == 0 or seo.images_with_alt / max(seo.images_total, 1) >= 0.5,
             f"{seo.images_with_alt}/{seo.images_total}" if seo.images_total else "—"),
            ("Canonical tag", seo.has_canonical, None),
            ("Schema markup", seo.has_schema, ", ".join(seo.schema_types) if seo.schema_types else None),
            ("OG tags (redes)", bool(seo.og_title and seo.og_image), None),
            ("Twitter card", seo.has_twitter_card, None),
        ]
        rows = [["Check", "Estado", "Detalle"]]
        for name, ok, detail in checks:
            rows.append([name, "✓" if ok else "✗", detail or ""])
        _add_info_table(story, rows, col_widths=[70 * mm, 20 * mm, 70 * mm])

    # ── HOSTING ────────────────────────────────────────────────────────────────
    if result.hosting:
        story.append(Paragraph("Hosting e Infraestructura", section_style))
        h = result.hosting
        rows = [["Campo", "Valor"]]
        if h.ip:
            rows.append(["IP del servidor", h.ip])
        if h.provider:
            rows.append(["Proveedor hosting", h.provider])
        if h.country and h.city:
            rows.append(["Ubicación", f"{h.city}, {h.country}"])
        if h.mx_provider:
            rows.append(["Email (MX)", h.mx_provider])
        if h.domain_registered:
            rows.append(["Dominio registrado", h.domain_registered])
        if h.domain_expires:
            rows.append(["Dominio vence", h.domain_expires])
        _add_info_table(story, rows)

    # ── CONTACTS ───────────────────────────────────────────────────────────────
    if result.contacts:
        story.append(Paragraph("Contacto detectado", section_style))
        c = result.contacts
        rows = [["Campo", "Valor"]]
        if c.emails:
            rows.append(["Emails", ", ".join(c.emails)])
        if c.phones:
            rows.append(["Teléfonos", ", ".join(c.phones)])
        if c.social:
            for platform, link in c.social.items():
                rows.append([platform.capitalize(), link])
        if c.contact_name:
            rows.append(["Responsable", c.contact_name])
        _add_info_table(story, rows)

    # ── COMPLIANCE ─────────────────────────────────────────────────────────────
    if result.compliance:
        story.append(Paragraph("Compliance y Analytics", section_style))
        comp = result.compliance
        checks = [
            ("Banner de cookies", comp.has_cookie_banner),
            ("Política de privacidad", comp.has_privacy_policy),
            ("Google Analytics 4", comp.has_ga4),
            ("Google Tag Manager", comp.has_gtm),
            ("Meta Pixel", comp.has_meta_pixel),
            ("Hotjar", comp.has_hotjar),
            ("Microsoft Clarity", comp.has_clarity),
        ]
        rows = [["Item", "Estado"]]
        for name, ok in checks:
            rows.append([name, "✓ Sí" if ok else "✗ No"])
        _add_info_table(story, rows, col_widths=[100 * mm, 60 * mm])

    # ── BACK COVER CTA ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 10 * mm))
    story.append(HRFlowable(width="100%", thickness=2, color=ECLYPSE_BLUE, spaceAfter=8))
    cta_data = [[
        Paragraph("<b>¿Querés que lo resolvamos?</b>", style("cta_h", fontSize=14, textColor=ECLYPSE_DARK, fontName="Helvetica-Bold")),
        Paragraph("Eclypse resuelve todos los problemas detectados en este reporte.<br/>"
                  "Mantenimiento · Seguridad · Performance · SEO · Hosting<br/>"
                  "<b>contacto@eclypsedesign.com · eclypsedesign.com</b>",
                  style("cta_b", fontSize=9, textColor=ECLYPSE_DARK)),
    ]]
    cta_table = Table(cta_data, colWidths=[80 * mm, 90 * mm])
    cta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ECLYPSE_LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    story.append(cta_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    return filepath


def _add_info_table(story, rows, col_widths=None):
    if col_widths is None:
        col_widths = [55 * mm, 115 * mm]
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ECLYPSE_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [ECLYPSE_LIGHT, colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDDD")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(t)
    story.append(Spacer(1, 4 * mm))

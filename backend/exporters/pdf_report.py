from __future__ import annotations

import io
import base64
import os
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas as pdfcanvas

from backend.models import AnalysisResult, Severity

ECLYPSE_BLUE = colors.HexColor("#0057FF")
ECLYPSE_DARK = colors.HexColor("#0A0A0A")
ECLYPSE_LIGHT = colors.HexColor("#F5F7FA")
COLOR_CRITICAL = colors.HexColor("#FF3B3B")
COLOR_WARNING = colors.HexColor("#FFAA00")
COLOR_INFO = colors.HexColor("#00B4D8")
COLOR_OK = colors.HexColor("#22C55E")

# Severity hex strings — used for XML-safe inline color in Paragraph markup
_SEV_HEX = {
    Severity.critical: "FF3B3B",
    Severity.warning: "FFAA00",
    Severity.info: "00B4D8",
}
_SEV_LABEL = {
    Severity.critical: "CRÍTICO",
    Severity.warning: "ATENCIÓN",
    Severity.info: "INFO",
}

W, H = A4

# ── Styles defined once at module level to avoid ParagraphStyle name collisions ──
_base = getSampleStyleSheet()

def _ps(name: str, parent: str = "Normal", **kw) -> ParagraphStyle:
    return ParagraphStyle(name, parent=_base[parent], **kw)

STYLES = {
    "h1_custom":    _ps("wi_h1", fontSize=22, textColor=ECLYPSE_DARK, spaceAfter=4, fontName="Helvetica-Bold"),
    "subtitle":     _ps("wi_subtitle", fontSize=11, textColor=colors.HexColor("#555555"), spaceAfter=12),
    "section":      _ps("wi_section", fontSize=13, textColor=ECLYPSE_BLUE, spaceAfter=6, spaceBefore=14, fontName="Helvetica-Bold"),
    "body":         _ps("wi_body", fontSize=9, textColor=ECLYPSE_DARK, spaceAfter=4),
    "small":        _ps("wi_small", fontSize=8, textColor=colors.HexColor("#666666")),
    "bold":         _ps("wi_bold", fontSize=9, textColor=ECLYPSE_DARK, fontName="Helvetica-Bold"),
    "center":       _ps("wi_center", fontSize=9, alignment=TA_CENTER),
    "cover_brand":  _ps("wi_cover_brand", fontSize=10, textColor=ECLYPSE_BLUE, fontName="Helvetica-Bold", spaceAfter=2),
    "cover_title":  _ps("wi_cover_title", fontSize=26, textColor=ECLYPSE_DARK, fontName="Helvetica-Bold", spaceAfter=4),
    "sc":           _ps("wi_sc", fontSize=32, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_CENTER),
    "lb":           _ps("wi_lb", fontSize=14, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_CENTER),
    "cta_h":        _ps("wi_cta_h", fontSize=14, textColor=ECLYPSE_DARK, fontName="Helvetica-Bold"),
    "cta_b":        _ps("wi_cta_b", fontSize=9, textColor=ECLYPSE_DARK),
}


class NumberedCanvas(pdfcanvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []

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

    def _draw_footer(self, total: int):
        self.saveState()
        self.setFillColor(colors.HexColor("#888888"))
        self.setFont("Helvetica", 8)
        self.drawRightString(W - 20 * mm, 10 * mm, f"Página {self._pageNumber} de {total}")
        self.drawString(20 * mm, 10 * mm, "Eclypse Web Intelligence · eclypsedesign.com")
        self.restoreState()


def _score_color(score: int) -> colors.Color:
    if score >= 70:
        return COLOR_CRITICAL
    if score >= 40:
        return COLOR_WARNING
    return COLOR_OK


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


def _p(text: str, style_key: str) -> Paragraph:
    return Paragraph(text, STYLES[style_key])


def generate(result: AnalysisResult, output_dir: str = "./pdfs") -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filepath = os.path.join(output_dir, f"{result.job_id}.pdf")

    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )

    story = []

    # ── COVER ──────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 10 * mm))
    story.append(_p("ECLYPSE", "cover_brand"))
    story.append(_p("Web Intelligence Analyzer", "cover_title"))
    story.append(HRFlowable(width="100%", thickness=2, color=ECLYPSE_BLUE, spaceAfter=10))
    story.append(_p(f"Análisis de: <b>{xml_escape(result.domain)}</b>", "subtitle"))
    story.append(_p(f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", "small"))
    if result.name:
        story.append(_p(f"Preparado para: {xml_escape(result.name)}", "small"))
    story.append(Spacer(1, 8 * mm))

    # Score pill
    score_val = result.score.total if result.score else 0
    label = result.score.label if result.score else ""
    score_color = _score_color(score_val)

    score_table = Table(
        [[_p(f"<b>{score_val}/100</b>", "sc"), _p(f"<b>{xml_escape(label)}</b>", "lb")]],
        colWidths=[50 * mm, 100 * mm], rowHeights=[22 * mm],
    )
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), score_color),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 6 * mm))

    # Score breakdown
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
        story.append(_p("Principales problemas detectados", "section"))
        for issue in result.score.top_issues:
            hex_color = _SEV_HEX[issue.severity]
            sev_label = _SEV_LABEL[issue.severity]
            row = [[
                _p(f"<font color='#{hex_color}'><b>{sev_label}</b></font>", "body"),
                _p(f"<b>{xml_escape(issue.message)}</b>", "body"),
                _p(xml_escape(issue.detail or ""), "small"),
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
        story.append(_p("CMS y Tecnología", "section"))
        cms = result.cms
        rows = [["Campo", "Valor"],
                ["CMS detectado", xml_escape(cms.cms or "Desconocido")],
                ["Versión", xml_escape(cms.version or "—")],
                ["Tema activo", xml_escape(cms.theme or "—")],
                ["Plugins detectados", str(len(cms.plugins))]]
        _add_info_table(story, rows)

    # ── SECURITY ───────────────────────────────────────────────────────────────
    if result.security:
        story.append(_p("Seguridad", "section"))
        sec = result.security
        missing_h = [h for h, v in sec.headers.items() if v is None]
        rows = [["Campo", "Valor"],
                ["SSL válido", "✓ Sí" if sec.ssl_valid else "✗ No"],
                ["Emisor SSL", xml_escape(sec.ssl_issuer or "—")],
                ["Días para vencer", str(sec.ssl_days_left) if sec.ssl_days_left is not None else "—"],
                ["Headers faltantes", xml_escape(", ".join(missing_h)) if missing_h else "Ninguno"],
                ["Archivos expuestos", xml_escape(", ".join(sec.exposed_files)) if sec.exposed_files else "Ninguno"]]
        _add_info_table(story, rows)

    # ── PERFORMANCE ────────────────────────────────────────────────────────────
    if result.performance:
        story.append(_p("Performance", "section"))
        perf = result.performance
        rows = [["Métrica", "Valor"],
                ["Score mobile", f"{perf.mobile_score}/100" if perf.mobile_score is not None else "—"],
                ["Score desktop", f"{perf.desktop_score}/100" if perf.desktop_score is not None else "—"],
                ["LCP", f"{perf.lcp}s" if perf.lcp else "—"],
                ["FCP", f"{perf.fcp}s" if perf.fcp else "—"],
                ["CLS", str(perf.cls) if perf.cls is not None else "—"],
                ["TTFB", f"{perf.ttfb}s" if perf.ttfb else "—"],
                ["CDN", f"✓ {xml_escape(perf.cdn_provider or '')}" if perf.uses_cdn else "✗ No usa CDN"]]
        _add_info_table(story, rows)

        if perf.screenshot_mobile:
            try:
                story.append(_p("Vista mobile del sitio", "bold"))
                img_data = perf.screenshot_mobile
                if img_data.startswith("data:"):
                    img_data = img_data.split(",", 1)[1]
                img_bytes = base64.b64decode(img_data)
                from reportlab.platypus import Image as RLImage
                img = RLImage(io.BytesIO(img_bytes), width=60 * mm, height=100 * mm)
                story.append(img)
                story.append(Spacer(1, 4 * mm))
            except Exception:
                pass

    # ── SEO ────────────────────────────────────────────────────────────────────
    if result.seo:
        story.append(_p("SEO", "section"))
        seo = result.seo
        alt_pct = seo.images_with_alt / max(seo.images_total, 1)
        checks = [
            ["Check", "Estado", "Detalle"],
            ["Meta title", "✓" if seo.has_meta_title else "✗", xml_escape(seo.meta_title or "")],
            ["Meta description", "✓" if seo.has_meta_description else "✗", ""],
            ["robots.txt", "✓ OK" if seo.has_robots_txt and not seo.robots_blocks_google else ("⚠ Bloquea Google" if seo.robots_blocks_google else "✗ No existe"), ""],
            ["sitemap.xml", "✓" if seo.has_sitemap else "✗", ""],
            ["H1 tag", f"{seo.h1_count}", ""],
            ["Alt text imágenes", f"{seo.images_with_alt}/{seo.images_total}", ""],
            ["Canonical", "✓" if seo.has_canonical else "✗", ""],
            ["Schema markup", "✓ " + xml_escape(", ".join(seo.schema_types)) if seo.has_schema else "✗", ""],
            ["OG tags", "✓" if seo.og_title and seo.og_image else "✗", ""],
            ["Twitter card", "✓" if seo.has_twitter_card else "✗", ""],
        ]
        _add_info_table(story, checks, col_widths=[60 * mm, 25 * mm, 85 * mm])

    # ── HOSTING ────────────────────────────────────────────────────────────────
    if result.hosting:
        story.append(_p("Hosting e Infraestructura", "section"))
        h = result.hosting
        rows = [["Campo", "Valor"],
                ["IP del servidor", xml_escape(h.ip or "—")],
                ["Proveedor hosting", xml_escape(h.provider or "—")],
                ["Ubicación", xml_escape(f"{h.city}, {h.country}" if h.city and h.country else (h.country or "—"))],
                ["Email (MX)", xml_escape(h.mx_provider or "—")],
                ["Dominio registrado", xml_escape(h.domain_registered or "—")],
                ["Dominio vence", xml_escape(h.domain_expires or "—")]]
        _add_info_table(story, rows)

    # ── CONTACTS ───────────────────────────────────────────────────────────────
    if result.contacts:
        story.append(_p("Contacto detectado", "section"))
        c = result.contacts
        rows = [["Campo", "Valor"],
                ["Emails", xml_escape(", ".join(c.emails)) if c.emails else "No detectado"],
                ["Teléfonos", xml_escape(", ".join(c.phones)) if c.phones else "No detectado"],
                ["Responsable", xml_escape(c.contact_name or "—")]]
        for platform, link in (c.social or {}).items():
            rows.append([xml_escape(platform.capitalize()), xml_escape(str(link))])
        _add_info_table(story, rows)

    # ── COMPLIANCE ─────────────────────────────────────────────────────────────
    if result.compliance:
        story.append(_p("Compliance y Analytics", "section"))
        comp = result.compliance
        checks = [["Item", "Estado"],
                  ["Banner de cookies", "✓ Sí" if comp.has_cookie_banner else "✗ No"],
                  ["Política de privacidad", "✓ Sí" if comp.has_privacy_policy else "✗ No"],
                  ["Google Analytics 4", "✓ Sí" if comp.has_ga4 else "✗ No"],
                  ["Google Tag Manager", "✓ Sí" if comp.has_gtm else "✗ No"],
                  ["Meta Pixel", "✓ Sí" if comp.has_meta_pixel else "✗ No"],
                  ["Hotjar", "✓ Sí" if comp.has_hotjar else "✗ No"],
                  ["Microsoft Clarity", "✓ Sí" if comp.has_clarity else "✗ No"]]
        _add_info_table(story, checks, col_widths=[100 * mm, 60 * mm])

    # ── BACK COVER CTA ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 10 * mm))
    story.append(HRFlowable(width="100%", thickness=2, color=ECLYPSE_BLUE, spaceAfter=8))
    cta_data = [[
        _p("<b>¿Querés que lo resolvamos?</b>", "cta_h"),
        _p("Eclypse resuelve todos los problemas de este reporte.<br/>"
           "Mantenimiento · Seguridad · Performance · SEO · Hosting<br/>"
           "<b>contacto@eclypsedesign.com · eclypsedesign.com</b>", "cta_b"),
    ]]
    cta_table = Table(cta_data, colWidths=[80 * mm, 90 * mm])
    cta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ECLYPSE_LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(cta_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    return filepath

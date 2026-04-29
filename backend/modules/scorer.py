from backend.models import (
    CMSResult, SecurityResult, PerformanceResult,
    HostingResult, SEOResult, ComplianceResult,
    ScoreResult, Issue, Severity
)


def calculate(
    cms: CMSResult | None,
    security: SecurityResult | None,
    performance: PerformanceResult | None,
    hosting: HostingResult | None,
    seo: SEOResult | None,
    compliance: ComplianceResult | None,
) -> ScoreResult:
    score = 0
    breakdown = {}
    all_issues: list[Issue] = []

    # --- CMS ---
    cms_score = 0
    if cms:
        all_issues.extend(cms.issues)
        if cms.cms == "WordPress":
            wp_outdated = any("desactualizado" in i.message for i in cms.issues)
            plugins_vuln = any("plugins sin actualizar" in i.message for i in cms.issues)
            if wp_outdated:
                cms_score += 20
            if plugins_vuln:
                cms_score += 30
    breakdown["CMS"] = cms_score
    score += cms_score

    # --- Security ---
    sec_score = 0
    if security:
        all_issues.extend(security.issues)
        if security.ssl_valid is False:
            sec_score += 25
        elif security.ssl_days_left is not None and security.ssl_days_left < 30:
            sec_score += 20
        elif security.ssl_days_left is not None and security.ssl_days_left < 60:
            sec_score += 10
        if security.exposed_files:
            sec_score += 20
        if security.cves:
            sec_score += len(security.cves) * 5
        missing = [h for h, v in security.headers.items() if v is None]
        if len(missing) >= 3:
            sec_score += 10
    breakdown["Seguridad"] = sec_score
    score += sec_score

    # --- Performance ---
    perf_score = 0
    if performance:
        all_issues.extend(performance.issues)
        mobile = performance.mobile_score
        if mobile is not None:
            if mobile < 50:
                perf_score += 15
            elif mobile < 70:
                perf_score += 8
        if not performance.uses_cdn:
            perf_score += 5
    breakdown["Performance"] = perf_score
    score += perf_score

    # --- Hosting ---
    host_score = 0
    if hosting:
        all_issues.extend(hosting.issues)
        for issue in hosting.issues:
            if "dominio vence" in issue.message.lower() and issue.severity == Severity.critical:
                host_score += 15
    breakdown["Hosting"] = host_score
    score += host_score

    # --- SEO ---
    seo_score = 0
    if seo:
        all_issues.extend(seo.issues)
        if not seo.has_meta_title:
            seo_score += 10
        if not seo.has_meta_description:
            seo_score += 5
        if not seo.has_sitemap:
            seo_score += 5
        if seo.robots_blocks_google:
            seo_score += 15
        if seo.h1_count == 0:
            seo_score += 5
        if seo.images_total > 0 and (seo.images_with_alt / seo.images_total) < 0.5:
            seo_score += 5
        if not seo.has_schema:
            seo_score += 3
    breakdown["SEO"] = seo_score
    score += seo_score

    # --- Compliance ---
    comp_score = 0
    if compliance:
        all_issues.extend(compliance.issues)
        if not compliance.has_cookie_banner:
            comp_score += 7
        if not compliance.has_privacy_policy:
            comp_score += 5
        if not compliance.has_ga4 and not compliance.has_gtm:
            comp_score += 8
    breakdown["Compliance"] = comp_score
    score += comp_score

    score = min(score, 100)

    # Sort issues by severity
    priority = {Severity.critical: 0, Severity.warning: 1, Severity.info: 2}
    top_issues = sorted(all_issues, key=lambda i: priority[i.severity])[:8]

    if score >= 70:
        label = "LEAD CALIENTE"
    elif score >= 40:
        label = "OPORTUNIDAD MEDIA"
    else:
        label = "SITIO SALUDABLE"

    return ScoreResult(total=score, breakdown=breakdown, top_issues=top_issues, label=label)

from pydantic import BaseModel, HttpUrl, field_validator
from typing import Optional
from enum import Enum


class Severity(str, Enum):
    critical = "critical"
    warning = "warning"
    info = "info"


class Issue(BaseModel):
    severity: Severity
    message: str
    detail: Optional[str] = None


class AnalysisRequest(BaseModel):
    url: str
    name: Optional[str] = None
    email: Optional[str] = None

    @field_validator("url")
    @classmethod
    def normalize_url(cls, v: str) -> str:
        v = v.strip().lower()
        if not v.startswith(("http://", "https://")):
            v = "https://" + v
        return v


class ProgressEvent(BaseModel):
    module: str
    percent: int
    message: str


class CMSResult(BaseModel):
    cms: Optional[str] = None
    version: Optional[str] = None
    theme: Optional[str] = None
    plugins: list[dict] = []
    issues: list[Issue] = []


class SecurityResult(BaseModel):
    ssl_valid: Optional[bool] = None
    ssl_issuer: Optional[str] = None
    ssl_days_left: Optional[int] = None
    ssl_grade: Optional[str] = None
    headers: dict = {}
    exposed_files: list[str] = []
    cves: list[dict] = []
    issues: list[Issue] = []


class PerformanceResult(BaseModel):
    mobile_score: Optional[int] = None
    desktop_score: Optional[int] = None
    lcp: Optional[float] = None
    fcp: Optional[float] = None
    cls: Optional[float] = None
    ttfb: Optional[float] = None
    uses_cdn: bool = False
    cdn_provider: Optional[str] = None
    screenshot_mobile: Optional[str] = None
    issues: list[Issue] = []


class HostingResult(BaseModel):
    ip: Optional[str] = None
    asn: Optional[str] = None
    provider: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    mx_provider: Optional[str] = None
    domain_registered: Optional[str] = None
    domain_expires: Optional[str] = None
    issues: list[Issue] = []


class ContactResult(BaseModel):
    emails: list[str] = []
    phones: list[str] = []
    social: dict = {}
    contact_name: Optional[str] = None
    issues: list[Issue] = []


class SEOResult(BaseModel):
    has_meta_title: bool = False
    meta_title: Optional[str] = None
    meta_title_length: int = 0
    has_meta_description: bool = False
    meta_description: Optional[str] = None
    meta_description_length: int = 0
    has_robots_txt: bool = False
    robots_blocks_google: bool = False
    has_sitemap: bool = False
    h1_count: int = 0
    images_total: int = 0
    images_with_alt: int = 0
    has_canonical: bool = False
    has_schema: bool = False
    schema_types: list[str] = []
    og_title: Optional[str] = None
    og_image: Optional[str] = None
    og_description: Optional[str] = None
    has_twitter_card: bool = False
    issues: list[Issue] = []


class ComplianceResult(BaseModel):
    has_cookie_banner: bool = False
    has_privacy_policy: bool = False
    has_ga4: bool = False
    has_gtm: bool = False
    has_meta_pixel: bool = False
    has_hotjar: bool = False
    has_clarity: bool = False
    issues: list[Issue] = []


class ScoreResult(BaseModel):
    total: int = 0
    breakdown: dict = {}
    top_issues: list[Issue] = []
    label: str = ""


class AnalysisResult(BaseModel):
    job_id: str
    domain: str
    url: str
    name: Optional[str] = None
    email: Optional[str] = None
    cms: Optional[CMSResult] = None
    security: Optional[SecurityResult] = None
    performance: Optional[PerformanceResult] = None
    hosting: Optional[HostingResult] = None
    contacts: Optional[ContactResult] = None
    seo: Optional[SEOResult] = None
    compliance: Optional[ComplianceResult] = None
    score: Optional[ScoreResult] = None
    pdf_path: Optional[str] = None
    error: Optional[str] = None

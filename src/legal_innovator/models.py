"""Typed models for newsletter collection, ranking, rendering, and QA."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, arbitrary_types_allowed=False)


class SourceType(StrEnum):
    RSS = "rss"
    WEBPAGE = "webpage"
    SITEMAP = "sitemap"
    OPENAI_SEARCH = "openai_search"
    NEWS_API = "news_api"


class Region(StrEnum):
    IRELAND = "ireland"
    UK_EU = "uk_eu"
    US_GLOBAL = "us_global"
    GLOBAL = "global"
    UNKNOWN = "unknown"


class Source(Model):
    name: str
    url: AnyUrl
    type: SourceType
    region: Region = Region.UNKNOWN
    category: str = "general"
    credibility: float = Field(default=0.7, ge=0, le=1)
    paywalled: bool = False
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def require_http_url(cls, value: AnyUrl) -> AnyUrl:
        return _require_http_url(value)


class SourceLink(Model):
    name: str
    url: AnyUrl
    source_type: str = "source"

    @field_validator("url")
    @classmethod
    def require_http_url(cls, value: AnyUrl) -> AnyUrl:
        return _require_http_url(value)


class CandidateArticle(Model):
    title: str
    url: AnyUrl
    source_name: str
    source_url: AnyUrl | None = None
    source_type: SourceType = SourceType.WEBPAGE
    source_region: Region = Region.UNKNOWN
    source_credibility: float = Field(default=0.7, ge=0, le=1)
    paywalled: bool = False
    published_at: datetime | None = None
    snippet: str | None = None
    discovered_via: str = "source"

    @field_validator("url", "source_url")
    @classmethod
    def require_http_url(cls, value: AnyUrl | None) -> AnyUrl | None:
        if value is None:
            return None
        return _require_http_url(value)

    @property
    def canonical_url(self) -> str:
        return strip_tracking_params(str(self.url))

    @property
    def fingerprint(self) -> str:
        normalized = " ".join(self.title.lower().split())
        return hashlib.sha256(f"{normalized}|{self.canonical_url}".encode("utf-8")).hexdigest()[:16]


class ExtractedArticle(CandidateArticle):
    metadata_description: str | None = None
    article_text: str | None = Field(default=None, exclude=True, repr=False)
    extraction_notes: list[str] = Field(default_factory=list)
    access_limited: bool = False

    def safe_context(self, max_chars: int = 1600) -> str:
        parts = [self.title]
        if self.published_at:
            parts.append(f"Published: {self.published_at.date().isoformat()}")
        if self.snippet:
            parts.append(self.snippet)
        if self.metadata_description:
            parts.append(self.metadata_description)
        if self.article_text and not self.paywalled:
            parts.append(self.article_text[:max_chars])
        return "\n".join(part for part in parts if part)


class ClassificationResult(Model):
    article_url: AnyUrl
    in_scope: bool
    exclusion_reason: str | None = None
    is_opinion: bool = False
    is_vendor_only: bool = False
    is_factual_news_event: bool = True
    region: Region = Region.UNKNOWN
    legal_sector_relevance: float = Field(ge=0, le=1)
    innovation_significance: float = Field(ge=0, le=1)
    practical_impact: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    notes: str | None = None

    @field_validator("article_url")
    @classmethod
    def require_http_url(cls, value: AnyUrl) -> AnyUrl:
        return _require_http_url(value)


class StoryCluster(Model):
    cluster_id: str
    canonical_headline: str
    articles: list[ExtractedArticle]
    classification: ClassificationResult | None = None
    fingerprint: str

    @model_validator(mode="after")
    def require_articles(self) -> "StoryCluster":
        if not self.articles:
            raise ValueError("StoryCluster requires at least one article")
        return self


class ScoreBreakdown(Model):
    region: float = 0
    legal_relevance: float = 0
    innovation: float = 0
    practical_impact: float = 0
    source_credibility: float = 0
    recency: float = 0
    factuality: float = 0
    directness: float = 0


class RankedStory(Model):
    headline: str
    date: date
    canonical_url: AnyUrl
    sources: list[SourceLink] = Field(min_length=1, max_length=3)
    source_names: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    summary: str = ""
    why_it_matters: str = ""
    score: float = 0
    score_breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    confidence: float = 0.5
    qa_notes: list[str] = Field(default_factory=list)
    cluster_id: str = ""

    @field_validator("canonical_url")
    @classmethod
    def require_http_url(cls, value: AnyUrl) -> AnyUrl:
        return _require_http_url(value)

    @field_validator("source_names", mode="before")
    @classmethod
    def default_source_names(cls, value: Any) -> Any:
        return value or []


class Issue(Model):
    newsletter_name: str
    run_date: date
    generated_at: datetime
    window_start: date
    window_end: date
    intro: str
    stories: list[RankedStory]
    disclaimer: str = "This newsletter is for general information only and does not constitute legal advice."
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_story_count(self) -> "Issue":
        if len(self.stories) > 12:
            raise ValueError("Issue cannot contain more than 12 stories")
        return self


class QAFinding(Model):
    severity: Literal["info", "warning", "error"]
    message: str
    story_headline: str | None = None
    source_url: AnyUrl | None = None


class QAReport(Model):
    issue_date: date
    passed: bool
    findings: list[QAFinding] = Field(default_factory=list)
    stage_errors: list[str] = Field(default_factory=list)
    checklist: dict[str, bool] = Field(default_factory=dict)
    source_diagnostics: list["SourceDiagnostic"] = Field(default_factory=list)

    @property
    def warnings(self) -> list[QAFinding]:
        return [finding for finding in self.findings if finding.severity == "warning"]

    @property
    def errors(self) -> list[QAFinding]:
        return [finding for finding in self.findings if finding.severity == "error"]


class SourceDiagnostic(Model):
    name: str
    kind: str
    url_or_query: str
    candidates_found: int = 0
    status: Literal["ok", "warning", "error"] = "ok"
    notes: list[str] = Field(default_factory=list)


class OpenAIUsageLimits(Model):
    max_candidates: int = 150
    max_shortlist: int = 40
    max_final_stories: int = 12


def strip_tracking_params(url: str) -> str:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parsed = urlsplit(url)
    blocked_prefixes = ("utm_",)
    blocked_names = {"fbclid", "gclid", "mc_cid", "mc_eid"}
    params = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in blocked_names and not any(key.startswith(prefix) for prefix in blocked_prefixes)
    ]
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/") or "/", urlencode(params), ""))


def _require_http_url(value: AnyUrl) -> AnyUrl:
    if value.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are allowed")
    return value

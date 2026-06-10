"""Import Codex-researched candidate stories into the newsletter pipeline."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Literal

from pydantic import AnyUrl, Field, field_validator

from legal_innovator.config import RunWindow, Settings
from legal_innovator.errors import ErrorStage, StageError
from legal_innovator.models import (
    ClassificationResult,
    ExtractedArticle,
    Model,
    RankedStory,
    Region,
    SourceDiagnostic,
    SourceType,
    StoryCluster,
)
from legal_innovator.ranking import rank_clusters


SourceOrigin = Literal[
    "official_source",
    "confirmed_reporting",
    "reported_not_officially_confirmed",
    "secondary_reporting",
    "vendor_originated_announcement",
]


class ResearchedCandidate(Model):
    id: str
    headline: str
    published_date: date
    source_name: str
    source_url: AnyUrl
    event_type: str
    source_origin: SourceOrigin
    region: str
    factual_basis: str
    legal_sector_relevance_note: str
    duplicate_group: str = "none"
    warning_flags: list[str] = Field(default_factory=list)
    selected: bool = True

    @field_validator("source_url")
    @classmethod
    def require_http_url(cls, value: AnyUrl) -> AnyUrl:
        if value.scheme not in {"http", "https"}:
            raise ValueError("Only http and https URLs are allowed")
        return value

    @field_validator("warning_flags", mode="before")
    @classmethod
    def normalise_warning_flags(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            if value.strip().lower() == "none":
                return []
            return [part.strip() for part in re.split(r"[,;]", value) if part.strip()]
        if isinstance(value, list):
            return [str(part).strip() for part in value if str(part).strip().lower() != "none"]
        return [str(value)]


@dataclass(frozen=True)
class CandidateImportResult:
    candidates: list[ResearchedCandidate]
    clusters: list[StoryCluster]
    default_selected_cluster_ids: list[str]
    errors: list[StageError]
    diagnostics: list[SourceDiagnostic]


def load_candidate_file(path: str | Path, window: RunWindow) -> CandidateImportResult:
    candidate_path = Path(path)
    raw_text = candidate_path.read_text(encoding="utf-8")
    raw_items = _extract_candidate_items(raw_text)
    candidates = [ResearchedCandidate.model_validate(item) for item in raw_items]
    errors: list[StageError] = []
    clusters: list[StoryCluster] = []
    default_selected_cluster_ids: list[str] = []

    for candidate in candidates:
        published_at = datetime.combine(candidate.published_date, time(12, 0), tzinfo=window.run_at.tzinfo)
        if not (window.start_at <= published_at <= window.end_at):
            errors.append(
                StageError(
                    ErrorStage.EXTRACTION,
                    f"Candidate outside 14-day window: {candidate.id} ({candidate.published_date.isoformat()})",
                    source=candidate.source_name,
                    url=str(candidate.source_url),
                )
            )
            continue
        article = _article_from_candidate(candidate, published_at)
        classification = _classification_from_candidate(candidate)
        cluster = _cluster_from_candidate(candidate, article, classification)
        clusters.append(cluster)
        if candidate.selected:
            default_selected_cluster_ids.append(cluster.cluster_id)

    diagnostics = [
        SourceDiagnostic(
            name=candidate_path.name,
            kind="candidate_file",
            url_or_query=str(candidate_path),
            candidates_found=len(candidates),
            status="warning" if errors else "ok",
            notes=[f"{len(clusters)} candidate stories imported from Codex research output."],
        )
    ]
    return CandidateImportResult(
        candidates=candidates,
        clusters=clusters,
        default_selected_cluster_ids=default_selected_cluster_ids,
        errors=errors,
        diagnostics=diagnostics,
    )


def rank_imported_clusters(clusters: list[StoryCluster], window: RunWindow, settings: Settings) -> list[RankedStory]:
    """Build ranked stories while preserving the Codex-researched order."""

    ranked_by_id = {story.cluster_id: story for story in rank_clusters(clusters, window, settings)}
    stories: list[RankedStory] = []
    for index, cluster in enumerate(clusters):
        story = ranked_by_id.get(cluster.cluster_id)
        if not story:
            continue
        story.score = round(1000 - index + (story.score / 1000), 3)
        stories.append(story)
    return stories


def _extract_candidate_items(raw_text: str) -> list[dict[str, Any]]:
    text = _extract_json_text(raw_text)
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("candidates", "items", "stories"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("Candidate file must contain a JSON list or an object with a candidates/items/stories list.")


def _extract_json_text(raw_text: str) -> str:
    stripped = raw_text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        return stripped
    start_options = [index for index in (stripped.find("["), stripped.find("{")) if index != -1]
    if not start_options:
        return stripped
    start = min(start_options)
    end = max(stripped.rfind("]"), stripped.rfind("}"))
    return stripped[start : end + 1] if end > start else stripped


def _article_from_candidate(candidate: ResearchedCandidate, published_at: datetime) -> ExtractedArticle:
    warnings = ", ".join(candidate.warning_flags) if candidate.warning_flags else "none"
    metadata = (
        f"Event type: {candidate.event_type}\n"
        f"Source origin: {candidate.source_origin}\n"
        f"Warning flags: {warnings}\n"
        f"Legal-sector relevance: {candidate.legal_sector_relevance_note}"
    )
    return ExtractedArticle(
        title=candidate.headline,
        url=candidate.source_url,
        source_name=candidate.source_name,
        source_type=SourceType.WEBPAGE,
        source_region=_region_from_candidate(candidate.region),
        source_credibility=_source_credibility(candidate.source_origin),
        paywalled="paywalled" in {flag.lower() for flag in candidate.warning_flags},
        published_at=published_at,
        snippet=candidate.factual_basis,
        metadata_description=metadata,
        access_limited=bool(candidate.warning_flags),
        discovered_via=f"codex_candidate:{candidate.id}",
    )


def _classification_from_candidate(candidate: ResearchedCandidate) -> ClassificationResult:
    flags = {flag.lower() for flag in candidate.warning_flags}
    legal_relevance = 0.92 if candidate.region.lower() == "ireland" else 0.86
    innovation = _event_type_score(candidate.event_type)
    confidence = 0.82
    if "reported_not_confirmed" in flags or candidate.source_origin == "reported_not_officially_confirmed":
        confidence -= 0.12
    if "limited_detail" in flags or "date_uncertain" in flags:
        confidence -= 0.1
    if candidate.source_origin == "vendor_originated_announcement":
        confidence -= 0.07
    return ClassificationResult(
        article_url=candidate.source_url,
        in_scope=True,
        is_opinion=False,
        is_vendor_only=False,
        is_factual_news_event=True,
        region=_region_from_candidate(candidate.region),
        legal_sector_relevance=max(0.5, min(1.0, legal_relevance)),
        innovation_significance=max(0.4, min(1.0, innovation)),
        practical_impact=0.82,
        confidence=max(0.45, min(0.95, confidence)),
        notes="Imported from Codex-researched candidate file.",
    )


def _cluster_from_candidate(
    candidate: ResearchedCandidate,
    article: ExtractedArticle,
    classification: ClassificationResult,
) -> StoryCluster:
    return StoryCluster(
        cluster_id=candidate.id,
        canonical_headline=candidate.headline,
        articles=[article],
        classification=classification,
        fingerprint=candidate.id,
    )


def _region_from_candidate(value: str) -> Region:
    normalised = value.strip().lower().replace("-", "/")
    if normalised in {"ireland", "irish", "all-island", "all island"}:
        return Region.IRELAND
    if normalised in {"uk/eu", "uk", "eu", "uk and eu", "europe"}:
        return Region.UK_EU
    if normalised in {"us/global", "us", "usa", "global us"}:
        return Region.US_GLOBAL
    if normalised == "global":
        return Region.GLOBAL
    return Region.UNKNOWN


def _source_credibility(origin: SourceOrigin) -> float:
    return {
        "official_source": 0.95,
        "confirmed_reporting": 0.88,
        "reported_not_officially_confirmed": 0.78,
        "secondary_reporting": 0.72,
        "vendor_originated_announcement": 0.66,
    }[origin]


def _event_type_score(event_type: str) -> float:
    high = {
        "court_digitisation",
        "legal_ai_adoption",
        "access_to_justice",
        "legal_operations",
        "legal_education",
        "funding_acquisition_partnership",
        "reported_platform_entry",
    }
    medium = {
        "legal_tech_product",
        "professional_guidance",
    }
    if event_type in high:
        return 0.92
    if event_type in medium:
        return 0.82
    if event_type == "regulatory_development":
        return 0.6
    return 0.55

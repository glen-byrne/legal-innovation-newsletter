"""Configurable search adapter interfaces.

The MVP deliberately does not scrape search-engine result pages. Search is
represented as an adapter boundary so OpenAI web search or third-party APIs can
be enabled without coupling the rest of the pipeline to a provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from openai import OpenAI
from pydantic import AnyUrl, BaseModel, Field

from legal_innovator.config import RunWindow, Settings
from legal_innovator.errors import ErrorStage, StageError
from legal_innovator.models import CandidateArticle, Region, SourceType
from legal_innovator.sources.base import parse_datetime


class SearchProvider(ABC):
    errors: list[StageError]

    @abstractmethod
    def search(self, query: str, window: RunWindow, limit: int) -> list[CandidateArticle]:
        """Return candidate articles for a targeted query."""


class DisabledSearchProvider(SearchProvider):
    def __init__(self) -> None:
        self.errors: list[StageError] = []

    def search(self, query: str, window: RunWindow, limit: int) -> list[CandidateArticle]:
        return []


class SearchResultItem(BaseModel):
    title: str
    url: AnyUrl
    source_name: str
    published_at: str | None = None
    snippet: str | None = None
    region: Region = Region.UNKNOWN


class SearchResultBatch(BaseModel):
    items: list[SearchResultItem] = Field(default_factory=list)


class OpenAIWebSearchProvider(SearchProvider):
    """Optional OpenAI API web-search discovery provider."""

    def __init__(self, settings: Settings) -> None:
        settings.validate_for_live_ai()
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.errors: list[StageError] = []

    def search(self, query: str, window: RunWindow, limit: int) -> list[CandidateArticle]:
        if limit <= 0:
            return []
        try:
            response = self.client.responses.create(
                model=self.settings.openai_model_fast,
                tools=[{"type": "web_search_preview"}],
                input=_search_prompt(query, window, limit),
                temperature=0.1,
            )
            raw_text = getattr(response, "output_text", "") or "{}"
            batch = SearchResultBatch.model_validate_json(raw_text)
        except Exception as exc:  # noqa: BLE001 - optional discovery should degrade gracefully.
            self.errors.append(StageError(ErrorStage.SOURCE_ACCESS, f"OpenAI web search failed: {exc}", source=query))
            return []

        candidates: list[CandidateArticle] = []
        for item in batch.items[:limit]:
            published = _parse_search_date(item.published_at, window)
            if not published or not (window.start_at <= published.astimezone(window.run_at.tzinfo) <= window.end_at):
                continue
            candidates.append(
                CandidateArticle(
                    title=item.title,
                    url=item.url,
                    source_name=item.source_name,
                    source_type=SourceType.OPENAI_SEARCH,
                    source_region=item.region,
                    source_credibility=0.65,
                    paywalled=False,
                    published_at=published,
                    snippet=item.snippet,
                    discovered_via=f"openai_search:{query}",
                )
            )
        return candidates


def _search_prompt(query: str, window: RunWindow, limit: int) -> str:
    return (
        "Use web search to find recent legal innovation news. Return JSON only with an items array. "
        "Each item must include title, direct publisher url, source_name, published_at as ISO date or datetime, "
        "snippet, and region as ireland, uk_eu, us_global, global, or unknown. "
        "Do not return Google, Bing, or search-result URLs. Do not include opinion, commentary, advertorials, "
        "or vendor-only announcements. "
        f"Query: {query}\n"
        f"Window start: {window.start_at.isoformat()}\n"
        f"Window end: {window.end_at.isoformat()}\n"
        f"Maximum items: {limit}"
    )


def _parse_search_date(value: str | None, window: RunWindow) -> datetime | None:
    parsed = parse_datetime(value)
    if not parsed:
        return None
    return parsed.replace(tzinfo=window.run_at.tzinfo) if parsed.tzinfo is None else parsed

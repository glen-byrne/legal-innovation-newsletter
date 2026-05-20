"""Load sources and collect candidate articles."""

from __future__ import annotations

from pathlib import Path

import httpx
import yaml

from legal_innovator.config import RunWindow, Settings
from legal_innovator.errors import ErrorStage, StageError
from legal_innovator.models import CandidateArticle, Source, SourceType
from legal_innovator.sources.base import RobotsCache, unique_candidates
from legal_innovator.sources.rss import RSSSourceAdapter
from legal_innovator.sources.search import DisabledSearchProvider, OpenAIWebSearchProvider, SearchProvider
from legal_innovator.sources.sitemap import SitemapSourceAdapter
from legal_innovator.sources.webpage import WebPageSourceAdapter


class SourceConfig:
    def __init__(self, sources: list[Source], queries: list[str]) -> None:
        self.sources = sources
        self.queries = queries


def load_source_config(path: str | Path = "data/sources.yaml") -> SourceConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    sources = [Source(**item) for item in raw.get("sources", []) if item.get("enabled", True)]
    queries = [str(item) for item in raw.get("queries", [])]
    return SourceConfig(sources=sources, queries=queries)


class DiscoveryService:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        search_provider: SearchProvider | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or httpx.Client()
        self.robots = RobotsCache(self.client)
        self.adapters = {
            SourceType.RSS: RSSSourceAdapter(self.client, self.robots),
            SourceType.WEBPAGE: WebPageSourceAdapter(self.client, self.robots),
            SourceType.SITEMAP: SitemapSourceAdapter(self.client, self.robots),
        }
        if search_provider:
            self.search_provider = search_provider
        elif settings.enable_openai_web_search and not settings.dry_run_no_ai:
            self.search_provider = OpenAIWebSearchProvider(settings)
        else:
            self.search_provider = DisabledSearchProvider()
        self.errors: list[StageError] = []

    def collect(self, source_config: SourceConfig, window: RunWindow) -> list[CandidateArticle]:
        limit_per_source = max(5, self.settings.max_candidates // max(1, len(source_config.sources)))
        candidates: list[CandidateArticle] = []
        for source in source_config.sources:
            adapter = self.adapters.get(source.type)
            if not adapter:
                continue
            error_start = len(adapter.errors)
            try:
                candidates.extend(adapter.collect(source, window, limit_per_source))
            except Exception as exc:  # noqa: BLE001 - a single source should not stop discovery.
                self.errors.append(StageError(ErrorStage.SOURCE_ACCESS, str(exc), source=source.name, url=str(source.url)))
            self.errors.extend(adapter.errors[error_start:])

        remaining = max(0, self.settings.max_candidates - len(candidates))
        if remaining:
            per_query = max(1, remaining // max(1, len(source_config.queries)))
            for query in source_config.queries:
                candidates.extend(self.search_provider.search(query, window, per_query))
                if len(candidates) >= self.settings.max_candidates:
                    break

        self.errors.extend(self.robots.errors)
        self.errors.extend(getattr(self.search_provider, "errors", []))
        return unique_candidates(candidates)[: self.settings.max_candidates]

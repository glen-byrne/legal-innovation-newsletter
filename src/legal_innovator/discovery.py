"""Load sources and collect candidate articles."""

from __future__ import annotations

from pathlib import Path

import httpx
import yaml

from legal_innovator.config import RunWindow, Settings
from legal_innovator.errors import ErrorStage, StageError
from legal_innovator.models import CandidateArticle, Source, SourceDiagnostic, SourceType
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
        self.diagnostics: list[SourceDiagnostic] = []

    def collect(self, source_config: SourceConfig, window: RunWindow) -> list[CandidateArticle]:
        limit_per_source = max(5, self.settings.max_candidates // max(1, len(source_config.sources)))
        candidates: list[CandidateArticle] = []
        for source in source_config.sources:
            adapter = self.adapters.get(source.type)
            if not adapter:
                continue
            error_start = len(adapter.errors)
            before_count = len(candidates)
            notes: list[str] = []
            try:
                candidates.extend(adapter.collect(source, window, limit_per_source))
            except Exception as exc:  # noqa: BLE001 - a single source should not stop discovery.
                message = str(exc)
                self.errors.append(StageError(ErrorStage.SOURCE_ACCESS, message, source=source.name, url=str(source.url)))
                notes.append(message)
            new_errors = adapter.errors[error_start:]
            self.errors.extend(new_errors)
            notes.extend(error.message for error in new_errors[:3])
            found = len(candidates) - before_count
            self.diagnostics.append(
                SourceDiagnostic(
                    name=source.name,
                    kind=source.type.value,
                    url_or_query=str(source.url),
                    candidates_found=found,
                    status="error" if new_errors and found == 0 else "warning" if new_errors else "ok",
                    notes=notes,
                )
            )

        remaining = max(0, self.settings.max_candidates - len(candidates))
        if remaining and self.settings.enable_openai_web_search:
            per_query = max(1, remaining // max(1, len(source_config.queries)))
            for query in source_config.queries:
                error_start = len(getattr(self.search_provider, "errors", []))
                before_count = len(candidates)
                candidates.extend(self.search_provider.search(query, window, per_query))
                search_errors = getattr(self.search_provider, "errors", [])[error_start:]
                found = len(candidates) - before_count
                self.diagnostics.append(
                    SourceDiagnostic(
                        name=query,
                        kind="search",
                        url_or_query=query,
                        candidates_found=found,
                        status="error" if search_errors and found == 0 else "warning" if search_errors else "ok",
                        notes=[error.message for error in search_errors[:3]],
                    )
                )
                if len(candidates) >= self.settings.max_candidates:
                    break

        self.errors.extend(self.robots.errors)
        self.errors.extend(getattr(self.search_provider, "errors", []))
        return unique_candidates(candidates)[: self.settings.max_candidates]

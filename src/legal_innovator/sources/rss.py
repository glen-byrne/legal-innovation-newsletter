"""RSS/feed source discovery."""

from __future__ import annotations

from datetime import datetime

import feedparser

from legal_innovator.config import RunWindow
from legal_innovator.models import CandidateArticle, Source, SourceType
from legal_innovator.sources.base import SourceAdapter, in_window, normalize_url


class RSSSourceAdapter(SourceAdapter):
    def collect(self, source: Source, window: RunWindow, limit: int) -> list[CandidateArticle]:
        text = self.fetch_text(str(source.url), source)
        if not text:
            return []
        parsed = feedparser.parse(text)
        candidates: list[CandidateArticle] = []
        for entry in parsed.entries[: limit * 2]:
            link = getattr(entry, "link", None)
            title = getattr(entry, "title", None)
            if not link or not title:
                continue
            published_at = None
            if getattr(entry, "published_parsed", None):
                published_at = datetime(*entry.published_parsed[:6], tzinfo=window.run_at.tzinfo)
            elif getattr(entry, "updated_parsed", None):
                published_at = datetime(*entry.updated_parsed[:6], tzinfo=window.run_at.tzinfo)
            snippet = getattr(entry, "summary", None)
            candidate = CandidateArticle(
                title=title.strip(),
                url=normalize_url(link, str(source.url)),
                source_name=source.name,
                source_url=source.url,
                source_type=SourceType.RSS,
                source_region=source.region,
                source_credibility=source.credibility,
                paywalled=source.paywalled,
                published_at=published_at,
                snippet=snippet,
                discovered_via="rss",
            )
            if in_window(candidate, window):
                candidates.append(candidate)
            if len(candidates) >= limit:
                break
        return candidates

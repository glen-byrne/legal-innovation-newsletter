"""Public webpage source discovery."""

from __future__ import annotations

from bs4 import BeautifulSoup

from legal_innovator.config import RunWindow
from legal_innovator.models import CandidateArticle, Source, SourceType
from legal_innovator.sources.base import SourceAdapter, in_window, normalize_url, parse_datetime


class WebPageSourceAdapter(SourceAdapter):
    def collect(self, source: Source, window: RunWindow, limit: int) -> list[CandidateArticle]:
        html = self.fetch_text(str(source.url), source)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        candidates = self._extract_listing_candidates(soup, source, window)
        possibly_current = [candidate for candidate in candidates if candidate.published_at is None or in_window(candidate, window)]
        return possibly_current[:limit]

    def _extract_listing_candidates(
        self,
        soup: BeautifulSoup,
        source: Source,
        window: RunWindow,
    ) -> list[CandidateArticle]:
        candidates: list[CandidateArticle] = []
        for node in soup.select("article, .post, .entry, li"):
            link = node.select_one("a[href]")
            if not link:
                continue
            title = " ".join(link.get_text(" ", strip=True).split())
            href = link.get("href")
            if not title or not href or len(title) < 10:
                continue
            published_at = None
            time_node = node.select_one("time[datetime], time")
            if time_node:
                published_at = parse_datetime(time_node.get("datetime") or time_node.get_text(" ", strip=True))
            if published_at and published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=window.run_at.tzinfo)
            snippet_node = node.select_one("p, .excerpt, .summary")
            snippet = snippet_node.get_text(" ", strip=True) if snippet_node else None
            candidates.append(
                CandidateArticle(
                    title=title,
                    url=normalize_url(href, str(source.url)),
                    source_name=source.name,
                    source_url=source.url,
                    source_type=SourceType.WEBPAGE,
                    source_region=source.region,
                    source_credibility=source.credibility,
                    paywalled=source.paywalled,
                    published_at=published_at,
                    snippet=snippet,
                    discovered_via="webpage",
                )
            )
        if not candidates:
            candidates.extend(self._fallback_anchor_candidates(soup, source))
        return candidates

    def _fallback_anchor_candidates(self, soup: BeautifulSoup, source: Source) -> list[CandidateArticle]:
        candidates: list[CandidateArticle] = []
        for link in soup.select("a[href]"):
            title = " ".join(link.get_text(" ", strip=True).split())
            href = link.get("href")
            if not title or not href or len(title) < 16:
                continue
            if href.startswith("#") or href.startswith("mailto:"):
                continue
            candidates.append(
                CandidateArticle(
                    title=title,
                    url=normalize_url(href, str(source.url)),
                    source_name=source.name,
                    source_url=source.url,
                    source_type=SourceType.WEBPAGE,
                    source_region=source.region,
                    source_credibility=source.credibility,
                    paywalled=source.paywalled,
                    published_at=None,
                    discovered_via="webpage_anchor",
                )
            )
        return candidates

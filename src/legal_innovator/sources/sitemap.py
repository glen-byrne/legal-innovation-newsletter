"""Sitemap discovery adapter."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from legal_innovator.config import RunWindow
from legal_innovator.models import CandidateArticle, Source, SourceType
from legal_innovator.sources.base import SourceAdapter, in_window, normalize_url, parse_datetime


class SitemapSourceAdapter(SourceAdapter):
    def collect(self, source: Source, window: RunWindow, limit: int) -> list[CandidateArticle]:
        text = self.fetch_text(str(source.url), source)
        if not text:
            return []
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            return []

        candidates: list[CandidateArticle] = []
        for url_node in root.findall(".//{*}url"):
            loc = _node_text(url_node, "loc")
            if not loc:
                continue
            lastmod = parse_datetime(_node_text(url_node, "lastmod"))
            if lastmod and lastmod.tzinfo is None:
                lastmod = lastmod.replace(tzinfo=window.run_at.tzinfo)
            candidate = CandidateArticle(
                title=_title_from_url(loc),
                url=normalize_url(loc, str(source.url)),
                source_name=source.name,
                source_url=source.url,
                source_type=SourceType.SITEMAP,
                source_region=source.region,
                source_credibility=source.credibility,
                paywalled=source.paywalled,
                published_at=lastmod,
                discovered_via="sitemap",
            )
            if in_window(candidate, window):
                candidates.append(candidate)
            if len(candidates) >= limit:
                break
        return candidates


def _node_text(parent: ElementTree.Element, local_name: str) -> str | None:
    node = parent.find(f"{{*}}{local_name}")
    if node is None or not node.text:
        return None
    return node.text.strip()


def _title_from_url(url: str) -> str:
    path = unquote(urlsplit(url).path.rstrip("/"))
    slug = path.rsplit("/", maxsplit=1)[-1] or urlsplit(url).netloc
    title = slug.replace("-", " ").replace("_", " ").strip()
    return title.title() if title else url

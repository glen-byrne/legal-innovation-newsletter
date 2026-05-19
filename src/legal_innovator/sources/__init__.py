"""Source discovery adapters."""

from legal_innovator.sources.base import SourceAdapter
from legal_innovator.sources.rss import RSSSourceAdapter
from legal_innovator.sources.sitemap import SitemapSourceAdapter
from legal_innovator.sources.webpage import WebPageSourceAdapter

__all__ = ["SourceAdapter", "RSSSourceAdapter", "SitemapSourceAdapter", "WebPageSourceAdapter"]

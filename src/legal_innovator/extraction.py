"""Metadata and permitted article extraction."""

from __future__ import annotations

import json
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from legal_innovator.config import Settings
from legal_innovator.errors import ErrorStage, StageError
from legal_innovator.models import CandidateArticle, ExtractedArticle
from legal_innovator.sources.base import RobotsCache, USER_AGENT, parse_datetime


class ExtractionService:
    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client()
        self.robots = RobotsCache(self.client)
        self.errors: list[StageError] = []

    def extract_many(self, candidates: list[CandidateArticle]) -> list[ExtractedArticle]:
        extracted: list[ExtractedArticle] = []
        for candidate in candidates:
            article = self.extract(candidate)
            if article:
                extracted.append(article)
        self.errors.extend(self.robots.errors)
        return extracted

    def extract(self, candidate: CandidateArticle) -> ExtractedArticle | None:
        url = candidate.canonical_url
        if not self.robots.allowed(url):
            self.errors.append(
                StageError(ErrorStage.ROBOTS, "robots.txt disallows article extraction", candidate.source_name, url)
            )
            return ExtractedArticle(**candidate.model_dump(), access_limited=True, extraction_notes=["robots_disallowed"])

        try:
            response = self.client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=20)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            self.errors.append(StageError(ErrorStage.EXTRACTION, str(exc), candidate.source_name, url))
            return ExtractedArticle(**candidate.model_dump(), access_limited=True, extraction_notes=["fetch_failed"])

        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return ExtractedArticle(**candidate.model_dump(), access_limited=True, extraction_notes=["non_html"])

        soup = BeautifulSoup(response.text, "html.parser")
        description = _first_meta(
            soup,
            [
                ("name", "description"),
                ("property", "og:description"),
                ("name", "twitter:description"),
            ],
        )
        published_at = candidate.published_at or _extract_published_at(soup)
        if published_at and published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=self.settings.tzinfo)
        text = None
        notes: list[str] = []
        if candidate.paywalled:
            notes.append("paywalled_metadata_only")
        else:
            text = _extract_public_text(soup, self.settings.max_extract_chars_per_article)
            if not text:
                notes.append("no_public_article_text_found")
        return ExtractedArticle(
            **candidate.model_dump(exclude={"published_at"}),
            published_at=published_at,
            metadata_description=description,
            article_text=text,
            access_limited=candidate.paywalled or not bool(text),
            extraction_notes=notes,
        )


def _first_meta(soup: BeautifulSoup, selectors: list[tuple[str, str]]) -> str | None:
    for attr, value in selectors:
        node = soup.find("meta", attrs={attr: value})
        content = node.get("content") if node else None
        if content:
            return " ".join(content.split())
    return None


def _extract_published_at(soup: BeautifulSoup) -> datetime | None:
    meta_selectors = [
        ("property", "article:published_time"),
        ("name", "pubdate"),
        ("name", "date"),
        ("itemprop", "datePublished"),
    ]
    for attr, value in meta_selectors:
        node = soup.find("meta", attrs={attr: value})
        parsed = parse_datetime(node.get("content") if node else None)
        if parsed:
            return parsed
    time_node = soup.select_one("time[datetime], time")
    if time_node:
        return parse_datetime(time_node.get("datetime") or time_node.get_text(" ", strip=True))
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "{}")
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        for item in stack:
            if isinstance(item, dict):
                parsed = parse_datetime(str(item.get("datePublished") or item.get("dateCreated") or ""))
                if parsed:
                    return parsed
    return None


def _extract_public_text(soup: BeautifulSoup, max_chars: int) -> str | None:
    for node in soup(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
        node.decompose()
    containers = soup.select("article, main, .article-content, .entry-content, .post-content")
    if not containers:
        containers = [soup]
    paragraphs: list[str] = []
    for container in containers:
        for paragraph in container.select("p"):
            text = " ".join(paragraph.get_text(" ", strip=True).split())
            if len(text) >= 40:
                paragraphs.append(text)
            if sum(len(item) for item in paragraphs) >= max_chars:
                break
        if paragraphs:
            break
    joined = "\n\n".join(paragraphs)
    return joined[:max_chars] if joined else None

"""Base classes and helpers for source discovery."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from legal_innovator.config import RunWindow
from legal_innovator.errors import ErrorStage, StageError
from legal_innovator.models import CandidateArticle, Source, strip_tracking_params

LOGGER = logging.getLogger(__name__)
USER_AGENT = "TheIrishLegalInnovator/0.1 (+https://github.com/)"


class RobotsCache:
    """Small robots.txt cache for polite, compliance-safe fetch checks."""

    def __init__(self, client: httpx.Client, user_agent: str = USER_AGENT) -> None:
        self.client = client
        self.user_agent = user_agent
        self._cache: dict[str, RobotFileParser | None] = {}
        self.errors: list[StageError] = []

    def allowed(self, url: str) -> bool:
        parsed = urlsplit(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._cache:
            robots_url = urljoin(base, "/robots.txt")
            parser = RobotFileParser()
            parser.set_url(robots_url)
            try:
                response = self.client.get(robots_url, headers={"User-Agent": self.user_agent}, timeout=10)
                if response.status_code >= 400:
                    self._cache[base] = None
                else:
                    parser.parse(response.text.splitlines())
                    self._cache[base] = parser
            except httpx.HTTPError as exc:
                self.errors.append(
                    StageError(ErrorStage.ROBOTS, f"Could not read robots.txt: {exc}", url=robots_url)
                )
                self._cache[base] = None

        parser = self._cache[base]
        if parser is None:
            return True
        return parser.can_fetch(self.user_agent, url)


class SourceAdapter(ABC):
    def __init__(self, client: httpx.Client, robots: RobotsCache) -> None:
        self.client = client
        self.robots = robots
        self.errors: list[StageError] = []

    @abstractmethod
    def collect(self, source: Source, window: RunWindow, limit: int) -> list[CandidateArticle]:
        """Collect candidate articles from a source."""

    def fetch_text(self, url: str, source: Source) -> str | None:
        if not self.robots.allowed(url):
            self.errors.append(
                StageError(ErrorStage.ROBOTS, "robots.txt disallows fetching this URL", source=source.name, url=url)
            )
            return None
        try:
            response = self.client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=20)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type and "xml" not in content_type and "rss" not in content_type:
                self.errors.append(
                    StageError(
                        ErrorStage.SOURCE_ACCESS,
                        f"Unsupported content type: {content_type}",
                        source=source.name,
                        url=url,
                    )
                )
                return None
            return response.text
        except httpx.HTTPError as exc:
            self.errors.append(StageError(ErrorStage.SOURCE_ACCESS, str(exc), source=source.name, url=url))
            return None


def normalize_url(url: str, base_url: str | None = None) -> str:
    absolute = urljoin(base_url or "", url)
    parsed = urlsplit(strip_tracking_params(absolute))
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))


def is_http_url(url: str, base_url: str | None = None) -> bool:
    absolute = urljoin(base_url or "", url)
    parsed = urlsplit(absolute)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def unique_candidates(candidates: Iterable[CandidateArticle]) -> list[CandidateArticle]:
    seen: set[str] = set()
    unique: list[CandidateArticle] = []
    for candidate in candidates:
        key = candidate.canonical_url
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        return parsed
    except ValueError:
        try:
            return parsedate_to_datetime(cleaned)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None


def in_window(candidate: CandidateArticle, window: RunWindow) -> bool:
    if not candidate.published_at:
        return False
    published = candidate.published_at.astimezone(window.run_at.tzinfo)
    return window.start_at <= published <= window.end_at

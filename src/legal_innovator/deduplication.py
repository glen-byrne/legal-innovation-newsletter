"""AI-assisted story clustering and deterministic fallback deduplication."""

from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, Field

from legal_innovator.ai import StructuredAIClient
from legal_innovator.config import Settings
from legal_innovator.errors import ErrorStage, StageError
from legal_innovator.models import ClassificationResult, ExtractedArticle, StoryCluster
from legal_innovator.models import strip_tracking_params


class ClusterItem(BaseModel):
    cluster_id: str
    canonical_headline: str
    article_urls: list[str] = Field(default_factory=list)


class ClusterBatch(BaseModel):
    clusters: list[ClusterItem] = Field(default_factory=list)


DEDUP_SYSTEM = """You cluster news articles by underlying factual story for an executive legal innovation newsletter.
Return JSON only. Group together articles that report the same event even if headlines differ.
Do not group broad trend pieces together unless they are clearly about the same specific development.
"""


def cluster_articles(
    classified: list[tuple[ExtractedArticle, ClassificationResult]],
    settings: Settings,
    *,
    ai_client: StructuredAIClient | None = None,
) -> tuple[list[StoryCluster], list[StageError]]:
    errors: list[StageError] = []
    if not classified:
        return [], errors
    if settings.dry_run_no_ai:
        return _fallback_clusters(classified), errors
    if ai_client is None:
        ai_client = StructuredAIClient(settings)
    try:
        batch = ai_client.complete_json(
            schema=ClusterBatch,
            system=DEDUP_SYSTEM,
            user=_dedupe_prompt(classified),
            high_quality=True,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(StageError(ErrorStage.DEDUPLICATION, str(exc)))
        return _fallback_clusters(classified), errors
    by_url: dict[str, tuple[ExtractedArticle, ClassificationResult]] = {}
    for article, classification in classified:
        by_url[article.canonical_url.rstrip("/")] = (article, classification)
        by_url[str(article.url).rstrip("/")] = (article, classification)
    clusters: list[StoryCluster] = []
    used: set[str] = set()
    for item in batch.clusters:
        articles = []
        classifications = []
        for url in item.article_urls:
            match = by_url.get(strip_tracking_params(url).rstrip("/")) or by_url.get(url.rstrip("/"))
            if not match:
                continue
            article, classification = match
            articles.append(article)
            classifications.append(classification)
            used.add(url)
        if not articles:
            continue
        representative = max(classifications, key=lambda result: result.confidence)
        clusters.append(
            StoryCluster(
                cluster_id=item.cluster_id or _cluster_id(item.canonical_headline),
                canonical_headline=item.canonical_headline or articles[0].title,
                articles=articles,
                classification=representative,
                fingerprint=_fingerprint([article.title for article in articles]),
            )
        )
    for url, (article, classification) in by_url.items():
        if url not in used:
            clusters.append(_single_cluster(article, classification))
    return clusters, errors


def _dedupe_prompt(classified: list[tuple[ExtractedArticle, ClassificationResult]]) -> str:
    lines = ["Cluster these candidate articles by the same underlying factual story."]
    for index, (article, classification) in enumerate(classified, start=1):
        lines.append(
            f"\nItem {index}\nURL: {article.canonical_url}\nHeadline: {article.title}\n"
            f"Source: {article.source_name}\nDate: {article.published_at.date().isoformat() if article.published_at else 'unknown'}\n"
            f"Region: {classification.region}\nSnippet: {article.snippet or article.metadata_description or ''}"
        )
    return "\n".join(lines)


def _fallback_clusters(classified: list[tuple[ExtractedArticle, ClassificationResult]]) -> list[StoryCluster]:
    grouped: dict[str, list[tuple[ExtractedArticle, ClassificationResult]]] = {}
    for article, classification in classified:
        key = _fingerprint(_title_tokens(article.title)[:8])
        grouped.setdefault(key, []).append((article, classification))
    clusters: list[StoryCluster] = []
    for key, group in grouped.items():
        article, classification = group[0]
        clusters.append(
            StoryCluster(
                cluster_id=key,
                canonical_headline=article.title,
                articles=[item[0] for item in group],
                classification=classification,
                fingerprint=key,
            )
        )
    return clusters


def _single_cluster(article: ExtractedArticle, classification: ClassificationResult) -> StoryCluster:
    key = _cluster_id(article.title)
    return StoryCluster(
        cluster_id=key,
        canonical_headline=article.title,
        articles=[article],
        classification=classification,
        fingerprint=key,
    )


def _title_tokens(title: str) -> list[str]:
    stop = {"the", "a", "an", "to", "of", "and", "for", "in", "on", "with", "by", "as", "at"}
    return [token for token in re.findall(r"[a-z0-9]+", title.lower()) if token not in stop]


def _fingerprint(parts: list[str]) -> str:
    return hashlib.sha256(" ".join(parts).lower().encode("utf-8")).hexdigest()[:16]


def _cluster_id(title: str) -> str:
    return _fingerprint(_title_tokens(title)[:10])

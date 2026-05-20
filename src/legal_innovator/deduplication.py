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
    by_url: dict[str, str] = {}
    by_article_key: dict[str, tuple[ExtractedArticle, ClassificationResult]] = {}
    for article, classification in classified:
        key = _article_key(article)
        by_article_key[key] = (article, classification)
        by_url[article.canonical_url.rstrip("/")] = key
        by_url[str(article.url).rstrip("/")] = key
    clusters: list[StoryCluster] = []
    used_article_keys: set[str] = set()
    for item in batch.clusters:
        articles = []
        classifications = []
        for url in item.article_urls:
            article_key = by_url.get(strip_tracking_params(url).rstrip("/")) or by_url.get(url.rstrip("/"))
            if not article_key:
                continue
            match = by_article_key[article_key]
            article, classification = match
            articles.append(article)
            classifications.append(classification)
            used_article_keys.add(article_key)
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
    for article_key, (article, classification) in by_article_key.items():
        if article_key not in used_article_keys:
            clusters.append(_single_cluster(article, classification))
    return _merge_similar_clusters(clusters), errors


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
    return _merge_similar_clusters(clusters)


def _merge_similar_clusters(clusters: list[StoryCluster]) -> list[StoryCluster]:
    keyed: dict[str, list[StoryCluster]] = {}
    merged: list[StoryCluster] = []
    for cluster in clusters:
        key = _event_key(cluster)
        if not key:
            merged.append(cluster)
            continue
        keyed.setdefault(key, []).append(cluster)

    for group in keyed.values():
        if len(group) == 1:
            merged.append(group[0])
            continue
        articles: list[ExtractedArticle] = []
        classifications: list[ClassificationResult] = []
        for cluster in group:
            articles.extend(cluster.articles)
            if cluster.classification:
                classifications.append(cluster.classification)
        unique_articles = list({article.canonical_url: article for article in articles}.values())
        representative = max(classifications, key=lambda result: result.confidence) if classifications else None
        headline_source = max(unique_articles, key=lambda article: article.source_credibility)
        merged.append(
            StoryCluster(
                cluster_id=_cluster_id(headline_source.title),
                canonical_headline=headline_source.title,
                articles=unique_articles,
                classification=representative,
                fingerprint=_fingerprint([article.title for article in unique_articles]),
            )
        )
    return merged


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


def _event_key(cluster: StoryCluster) -> str | None:
    title = " ".join(article.title for article in cluster.articles)
    tokens = _distinctive_tokens(title)
    if not tokens:
        return None
    money = _money_marker(title)
    if money:
        return f"funding:{tokens[0]}:{money}"
    shared_event_terms = {"acquisition", "acquires", "funding", "integrates", "opens", "partners", "raises"}
    event_terms = [token for token in _title_tokens(title) if token in shared_event_terms]
    if event_terms and len(tokens) >= 2:
        return f"event:{tokens[0]}:{tokens[1]}:{event_terms[0]}"
    return None


def _distinctive_tokens(title: str) -> list[str]:
    generic = {
        "agentic",
        "announces",
        "artificial",
        "brings",
        "bringing",
        "funding",
        "intelligence",
        "legal",
        "law",
        "litigation",
        "million",
        "patent",
        "powered",
        "round",
        "seed",
        "startup",
        "technology",
        "unveils",
    }
    return [token for token in _title_tokens(title) if len(token) > 3 and token not in generic and not token.isdigit()]


def _money_marker(title: str) -> str | None:
    match = re.search(r"(?:[$€£]\s*)?(\d+(?:\.\d+)?)\s*(?:m|mn|million)\b", title.lower())
    if not match:
        return None
    return f"{match.group(1)}m"


def _article_key(article: ExtractedArticle) -> str:
    return strip_tracking_params(article.canonical_url).rstrip("/")


def _fingerprint(parts: list[str]) -> str:
    return hashlib.sha256(" ".join(parts).lower().encode("utf-8")).hexdigest()[:16]


def _cluster_id(title: str) -> str:
    return _fingerprint(_title_tokens(title)[:10])

"""Internal scoring and ranked story construction."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

from legal_innovator.config import RunWindow, Settings
from legal_innovator.models import Region, RankedStory, ScoreBreakdown, SourceLink, StoryCluster


REGION_WEIGHTS = {
    Region.IRELAND: 25.0,
    Region.UK_EU: 17.0,
    Region.US_GLOBAL: 10.0,
    Region.GLOBAL: 10.0,
    Region.UNKNOWN: 4.0,
}

MAINSTREAM_DOMAINS = ("bbc.", "theguardian.", "irishtimes.", "businesspost.", "reuters.", "apnews.", "ft.com")
OFFICIAL_DOMAINS = (".gov.", ".gov/", "europa.eu", "courts.ie", "justice.ie", "dataprotection.ie", "ico.org.uk")


def rank_clusters(clusters: list[StoryCluster], window: RunWindow, settings: Settings) -> list[RankedStory]:
    ranked = [_story_from_cluster(cluster, window, settings) for cluster in clusters if cluster.classification]
    return sorted(ranked, key=lambda story: story.score, reverse=True)


def _story_from_cluster(cluster: StoryCluster, window: RunWindow, settings: Settings) -> RankedStory:
    assert cluster.classification
    articles = sorted(
        cluster.articles,
        key=lambda article: (
            _source_order(_source_kind(str(article.url), article.source_name)),
            -article.source_credibility,
            article.published_at or datetime.min.replace(tzinfo=window.run_at.tzinfo),
        ),
    )
    primary = max(cluster.articles, key=lambda article: article.source_credibility)
    story_date = max((article.published_at for article in cluster.articles if article.published_at), default=window.run_at)
    breakdown = _score_breakdown(cluster, story_date, window)
    score = sum(breakdown.model_dump().values())
    links = [
        SourceLink(name=article.source_name, url=article.url, source_type=_source_kind(str(article.url), article.source_name))
        for article in articles[: settings.max_sources_per_story]
    ]
    return RankedStory(
        headline=cluster.canonical_headline,
        date=story_date.astimezone(window.run_at.tzinfo).date(),
        canonical_url=primary.url,
        sources=links,
        source_names=[link.name for link in links],
        source_types=[link.source_type for link in links],
        score=round(score, 3),
        score_breakdown=breakdown,
        confidence=cluster.classification.confidence,
        qa_notes=[],
        cluster_id=cluster.cluster_id,
    )


def _score_breakdown(cluster: StoryCluster, story_date: datetime, window: RunWindow) -> ScoreBreakdown:
    classification = cluster.classification
    assert classification
    age_seconds = max(0, (window.end_at - story_date.astimezone(window.run_at.tzinfo)).total_seconds())
    recency_ratio = max(0, 1 - (age_seconds / (14 * 24 * 60 * 60)))
    source_credibility = max((article.source_credibility for article in cluster.articles), default=0.5)
    legal = classification.legal_sector_relevance
    innovation = classification.innovation_significance
    impact = classification.practical_impact
    directness = 1.0 if legal >= 0.75 else 0.45
    return ScoreBreakdown(
        region=REGION_WEIGHTS.get(classification.region, REGION_WEIGHTS[Region.UNKNOWN]),
        legal_relevance=legal * 22,
        innovation=innovation * 17,
        practical_impact=impact * 17,
        source_credibility=source_credibility * 10,
        recency=recency_ratio * 8,
        factuality=5 if classification.is_factual_news_event else -8,
        directness=directness * 8,
    )


def _source_kind(url: str, name: str) -> str:
    domain = urlsplit(url).netloc.lower()
    if any(marker in domain or marker in url.lower() for marker in OFFICIAL_DOMAINS):
        return "official"
    if any(marker in domain for marker in MAINSTREAM_DOMAINS):
        return "mainstream_media"
    if any(term in name.lower() for term in ["law", "legal", "lawyer"]):
        return "legal_tech_media"
    return "other_media"


def _source_order(kind: str) -> int:
    order = {"official": 0, "mainstream_media": 1, "legal_tech_media": 2, "other_media": 3}
    return order.get(kind, 3)

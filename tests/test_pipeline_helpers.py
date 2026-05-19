from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from legal_innovator.config import Settings
from legal_innovator.deduplication import cluster_articles
from legal_innovator.models import ClassificationResult, ExtractedArticle, Region
from legal_innovator.ranking import rank_clusters


def article(title: str, url: str, region: Region = Region.IRELAND) -> ExtractedArticle:
    return ExtractedArticle(
        title=title,
        url=url,
        source_name="Example Legal News",
        source_url="https://example.com",
        source_region=region,
        source_credibility=0.8,
        published_at=datetime(2026, 5, 18, tzinfo=ZoneInfo("Europe/Dublin")),
        snippet="A legal technology development was reported.",
    )


def classification(url: str, region: Region) -> ClassificationResult:
    return ClassificationResult(
        article_url=url,
        in_scope=True,
        is_opinion=False,
        is_vendor_only=False,
        is_factual_news_event=True,
        region=region,
        legal_sector_relevance=0.9,
        innovation_significance=0.8,
        practical_impact=0.7,
        confidence=0.8,
    )


def test_deduplication_fallback_merges_same_story() -> None:
    settings = Settings(dry_run_no_ai=True)
    first = article("Irish courts launch digital filing pilot", "https://example.com/a")
    second = article("Irish courts launch digital filing pilot", "https://example.com/b")
    clusters, errors = cluster_articles(
        [(first, classification(str(first.url), Region.IRELAND)), (second, classification(str(second.url), Region.IRELAND))],
        settings,
    )
    assert not errors
    assert len(clusters) == 1
    assert len(clusters[0].articles) == 2


def test_irish_relevance_can_outrank_global_story() -> None:
    settings = Settings(dry_run_no_ai=True)
    irish = article("Irish law firm adopts AI governance platform", "https://example.com/irish", Region.IRELAND)
    global_item = article("Global legal AI product update", "https://example.com/global", Region.US_GLOBAL)
    clusters, _ = cluster_articles(
        [
            (irish, classification(str(irish.url), Region.IRELAND)),
            (global_item, classification(str(global_item.url), Region.US_GLOBAL)),
        ],
        settings,
    )
    run_at = datetime(2026, 5, 19, 12, 0, tzinfo=ZoneInfo("Europe/Dublin"))
    window = type("Window", (), {"start_at": run_at - timedelta(days=14), "end_at": run_at, "run_at": run_at})()
    ranked = rank_clusters(clusters, window, settings)
    assert ranked[0].headline == "Irish law firm adopts AI governance platform"


def test_missing_openai_env_fails_but_beehiiv_is_not_required() -> None:
    settings = Settings(openai_api_key=None, openai_model_fast=None, openai_model_high_quality=None)
    with pytest.raises(ValueError) as exc:
        settings.validate_for_live_ai()
    assert "OPENAI_API_KEY" in str(exc.value)
    assert "BEEHIIV" not in str(exc.value)

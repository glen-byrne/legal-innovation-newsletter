from __future__ import annotations

from legal_innovator.classification import _editorial_prefilter_reason
from legal_innovator.models import ExtractedArticle


def test_editorial_prefilter_excludes_commentary_and_podcasts() -> None:
    article = ExtractedArticle(
        title="Some Thoughts On Harvey's Launch of LAB",
        url="https://example.com/thoughts",
        source_name="LawNext",
    )

    assert _editorial_prefilter_reason(article) == "commentary_or_podcast"


def test_editorial_prefilter_allows_funding_news() -> None:
    article = ExtractedArticle(
        title="AI legal startup announces $10M funding round",
        url="https://example.com/funding",
        source_name="Example News",
        snippet="The company raises new funding from institutional investors.",
    )

    assert _editorial_prefilter_reason(article) is None

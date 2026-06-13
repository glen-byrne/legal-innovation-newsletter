"""AI-assisted relevance classification and exclusion filtering."""

from __future__ import annotations

from pydantic import BaseModel, Field

from legal_innovator.ai import StructuredAIClient
from legal_innovator.config import Settings
from legal_innovator.errors import ErrorStage, StageError
from legal_innovator.models import ClassificationResult, ExtractedArticle, Region


class ClassificationBatch(BaseModel):
    items: list[ClassificationResult] = Field(default_factory=list)


CLASSIFICATION_SYSTEM = """You are an executive legal innovation newsletter editor.
Classify candidate news items for The Legal Edge Ireland.
Return JSON only.
Exclude opinion, commentary, generic vendor marketing, and vendor-only product announcements unless there is a concrete factual news event supported by a reliable third-party source.
Treat paywalled items cautiously: use only headline, metadata, snippets, and links supplied. Do not infer detailed facts from a headline alone.
In scope includes AI in law, legal operations, court digitisation, regtech/compliance, e-discovery, access to justice, legal education, legal design, smart contracts/blockchain, privacy/cyber governance, alternative legal services, and legal-sector-relevant digital identity, cyber, AI regulation, or enterprise technology developments.
Give the strongest relevance to stories about how legal work is produced, delivered, automated, engineered, designed, governed, priced, taught, accessed, or supervised. Demote generic legal, litigation, regulatory, business, or technology-policy stories unless they have a clear legal-service-delivery or practice-of-law innovation angle.
"""


def classify_articles(
    articles: list[ExtractedArticle],
    settings: Settings,
    *,
    ai_client: StructuredAIClient | None = None,
) -> tuple[list[tuple[ExtractedArticle, ClassificationResult]], list[StageError]]:
    errors: list[StageError] = []
    if settings.dry_run_no_ai:
        return [(_article, _heuristic_classification(_article)) for _article in articles], errors
    if ai_client is None:
        ai_client = StructuredAIClient(settings)

    paired: list[tuple[ExtractedArticle, ClassificationResult]] = []
    for article in articles:
        prefilter_reason = _editorial_prefilter_reason(article)
        if prefilter_reason:
            continue
        try:
            batch = ai_client.complete_json(
                schema=ClassificationBatch,
                system=CLASSIFICATION_SYSTEM,
                user=_classification_prompt([article]),
                high_quality=False,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(StageError(ErrorStage.CLASSIFICATION, str(exc), article.source_name, article.canonical_url))
            continue
        if not batch.items:
            errors.append(
                StageError(ErrorStage.CLASSIFICATION, "AI returned no classification", article.source_name, article.canonical_url)
            )
            continue
        classification = batch.items[0]
        if not classification.in_scope:
            continue
        if classification.is_opinion or classification.is_vendor_only or not classification.is_factual_news_event:
            continue
        paired.append((article, classification))
    return paired, errors


def _editorial_prefilter_reason(article: ExtractedArticle) -> str | None:
    text = f"{article.title} {article.snippet or ''} {article.metadata_description or ''}".lower()
    commentary_markers = [
        "some thoughts",
        "opinion",
        "commentary",
        "podcast",
        "talkingtech podcast",
        "walk through:",
    ]
    vendor_markers = [
        "product award",
        "new product award",
        "launch of",
        "launches",
        "announces",
        "extends beyond software",
    ]
    if any(marker in text for marker in commentary_markers):
        return "commentary_or_podcast"
    if any(marker in text for marker in vendor_markers) and not _has_third_party_news_context(text):
        return "vendor_or_product_announcement"
    return None


def _has_third_party_news_context(text: str) -> bool:
    return any(marker in text for marker in ["funding", "raises", "acquisition", "court", "regulator", "government"])


def _classification_prompt(articles: list[ExtractedArticle]) -> str:
    lines = [
        "Classify these candidate articles. Return JSON with an items array.",
        "For every item include article_url, in_scope, exclusion_reason, is_opinion, is_vendor_only,",
        "is_factual_news_event, region, legal_sector_relevance, innovation_significance, practical_impact, confidence, notes.",
    ]
    for index, article in enumerate(articles, start=1):
        lines.append(
            f"\nItem {index}\n"
            f"URL: {article.canonical_url}\n"
            f"Source: {article.source_name}\n"
            f"Paywalled: {article.paywalled}\n"
            f"Context:\n{article.safe_context()[:2500]}"
        )
    return "\n".join(lines)


def _heuristic_classification(article: ExtractedArticle) -> ClassificationResult:
    text = f"{article.title} {article.snippet or ''} {article.metadata_description or ''}".lower()
    legal_terms = ["legal", "law", "court", "regulator", "compliance", "privacy", "counsel", "lawyer", "solicitor"]
    innovation_terms = ["ai", "technology", "digital", "automation", "cyber", "data", "platform", "software"]
    opinion_terms = ["opinion", "commentary", "column", "analysis:"]
    vendor_terms = ["launches", "announces", "press release"]
    region = Region.UNKNOWN
    if "ireland" in text or "irish" in text:
        region = Region.IRELAND
    elif "uk" in text or "eu " in text or "europe" in text:
        region = Region.UK_EU
    elif "global" in text or "us" in text:
        region = Region.US_GLOBAL
    legal_score = 0.85 if any(term in text for term in legal_terms) else 0.35
    innovation_score = 0.8 if any(term in text for term in innovation_terms) else 0.3
    is_opinion = any(term in text for term in opinion_terms)
    is_vendor_only = article.source_name.lower() in text and any(term in text for term in vendor_terms)
    in_scope = legal_score >= 0.5 and innovation_score >= 0.4 and not is_opinion and not is_vendor_only
    return ClassificationResult(
        article_url=article.url,
        in_scope=in_scope,
        exclusion_reason=None if in_scope else "heuristic_out_of_scope",
        is_opinion=is_opinion,
        is_vendor_only=is_vendor_only,
        is_factual_news_event=not is_opinion,
        region=region,
        legal_sector_relevance=legal_score,
        innovation_significance=innovation_score,
        practical_impact=0.6,
        confidence=0.35,
        notes="Heuristic dry-run classification; not suitable for publication.",
    )

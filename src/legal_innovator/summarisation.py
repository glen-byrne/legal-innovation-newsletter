"""AI-assisted story and issue summarisation."""

from __future__ import annotations

from pydantic import BaseModel, Field

from legal_innovator.ai import StructuredAIClient
from legal_innovator.config import Settings
from legal_innovator.errors import ErrorStage, StageError
from legal_innovator.models import ExtractedArticle, RankedStory, StoryCluster


class StorySummary(BaseModel):
    cluster_id: str
    headline: str
    summary: str
    why_it_matters: str


class SummaryBatch(BaseModel):
    intro: str
    stories: list[StorySummary] = Field(default_factory=list)


SUMMARY_SYSTEM = """You write The Legal Innovator Ireland, an executive briefing for law firm leaders, lawyers, clients, in-house counsel, and legal-tech founders.
Return JSON only. Tone: neutral, concise, professional, commercially aware. Avoid hype and legal advice.
Summaries must be based only on the supplied source snippets, metadata, and permitted article text. For paywalled sources, do not imply full article access.
Each story summary should be 1-2 concise sentences. Each why_it_matters should be exactly one sentence.
The intro should be 2-3 sentences summarising the main news from the fortnight.
"""


def summarise_issue(
    stories: list[RankedStory],
    clusters: list[StoryCluster],
    settings: Settings,
    *,
    ai_client: StructuredAIClient | None = None,
) -> tuple[str, list[RankedStory], list[StageError]]:
    errors: list[StageError] = []
    cluster_map = {cluster.cluster_id: cluster for cluster in clusters}
    if not stories:
        return _empty_issue_intro(), stories, errors
    if settings.dry_run_no_ai:
        for story in stories:
            cluster = cluster_map.get(story.cluster_id)
            story.summary = _fallback_summary(cluster.articles[0] if cluster else None)
            story.why_it_matters = "This may affect how legal teams assess technology, risk, or service delivery priorities."
        return _fallback_intro(stories), stories, errors
    if ai_client is None:
        ai_client = StructuredAIClient(settings)
    try:
        batch = ai_client.complete_json(
            schema=SummaryBatch,
            system=SUMMARY_SYSTEM,
            user=_summary_prompt(stories, cluster_map),
            high_quality=True,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(StageError(ErrorStage.SUMMARISATION, str(exc)))
        for story in stories:
            cluster = cluster_map.get(story.cluster_id)
            story.summary = _fallback_summary(cluster.articles[0] if cluster else None)
            story.why_it_matters = "This may affect how legal teams assess technology, risk, or service delivery priorities."
            story.qa_notes.append("AI summarisation failed; fallback summary used.")
        return _fallback_intro(stories), stories, errors

    by_cluster_id = {item.cluster_id: item for item in batch.stories}
    used_generated_ids: set[int] = set()
    for index, story in enumerate(stories):
        generated = by_cluster_id.get(story.cluster_id)
        if generated:
            used_generated_ids.add(id(generated))
        elif index < len(batch.stories) and id(batch.stories[index]) not in used_generated_ids:
            generated = batch.stories[index]
            used_generated_ids.add(id(generated))
        if not generated:
            story.qa_notes.append("No AI summary returned; fallback summary used.")
            cluster = cluster_map.get(story.cluster_id)
            story.summary = _fallback_summary(cluster.articles[0] if cluster else None)
            story.why_it_matters = "This may affect how legal teams assess technology, risk, or service delivery priorities."
            continue
        story.headline = generated.headline
        story.summary = generated.summary
        story.why_it_matters = generated.why_it_matters
    return batch.intro, stories, errors


def _summary_prompt(stories: list[RankedStory], cluster_map: dict[str, StoryCluster]) -> str:
    lines = [
        "Write the issue intro and final story summaries from these ranked stories.",
        "Return exactly one story object for each input story, in the same order.",
        "Preserve each Cluster ID exactly as supplied.",
    ]
    for index, story in enumerate(stories, start=1):
        cluster = cluster_map.get(story.cluster_id)
        lines.append(f"\nStory {index}\nCluster ID: {story.cluster_id}\nWorking headline: {story.headline}\nDate: {story.date}")
        if cluster:
            for article in cluster.articles[:3]:
                lines.append(
                    f"Source: {article.source_name}\nURL: {article.canonical_url}\n"
                    f"Paywalled: {article.paywalled}\nContext:\n{article.safe_context(1200)}"
                )
    return "\n".join(lines)


def _fallback_summary(article: ExtractedArticle | None) -> str:
    if not article:
        return "A legal innovation development was identified from reliable source metadata."
    return article.snippet or article.metadata_description or f"{article.source_name} reported the development."


def _fallback_intro(stories: list[RankedStory]) -> str:
    return (
        f"This issue tracks {len(stories)} legal innovation developments from the past fortnight, "
        "with priority given to Irish relevance and wider UK, EU, and global developments where they materially affect legal services."
    )


def _empty_issue_intro() -> str:
    return (
        "No qualified stories were selected for this run. Review the QA report for source access, date-window, "
        "classification, and extraction details before approving or rerunning the issue."
    )

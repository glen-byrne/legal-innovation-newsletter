"""Plain-text rendering from canonical Issue objects."""

from __future__ import annotations

from legal_innovator.models import Issue


def render_plaintext(issue: Issue) -> str:
    lines = [
        issue.newsletter_name,
        "=" * len(issue.newsletter_name),
        f"Issue date: {issue.run_date.isoformat()}",
        "",
        issue.intro,
        "",
    ]
    if not issue.stories:
        lines.extend(
            [
                "No qualified stories",
                "No stories met the source, date-window, relevance, and QA requirements for this run.",
                "",
            ]
        )
    for index, story in enumerate(issue.stories, start=1):
        regions = ", ".join(story.region_tags[:3]) or "Unspecified"
        lines.extend(
            [
                f"{index}. {story.headline}",
                f"Date: {story.date.isoformat()}",
                f"Regions: {regions}",
                story.summary,
                f"Why it matters: {story.why_it_matters}",
                "Sources:",
            ]
        )
        for link in story.sources:
            lines.append(f"- {link.name}: {link.url}")
        lines.append("")
    lines.extend([issue.disclaimer, ""])
    return "\n".join(lines)

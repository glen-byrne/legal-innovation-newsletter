"""Markdown rendering from canonical Issue objects."""

from __future__ import annotations

from legal_innovator.models import Issue


def render_markdown(issue: Issue) -> str:
    lines = [
        f"# {issue.newsletter_name}",
        "",
        f"**Issue date:** {issue.run_date.isoformat()}",
        "",
        issue.intro,
        "",
    ]
    if not issue.stories:
        lines.extend(
            [
                "## No Qualified Stories",
                "",
                "No stories met the source, date-window, relevance, and QA requirements for this run.",
                "",
            ]
        )
    for index, story in enumerate(issue.stories, start=1):
        regions = ", ".join(story.region_tags)
        lines.extend(
            [
                f"## {index}. {story.headline}",
                "",
                f"**Date:** {story.date.isoformat()}",
                "",
                f"**Regions:** {regions}" if regions else "**Regions:** Unspecified",
                "",
                story.summary,
                "",
                f"**Impact:** {story.why_it_matters}",
                "",
                "**Sources:** "
                + "; ".join(f"[{link.name}]({link.url})" for link in story.sources),
                "",
            ]
        )
    lines.extend(["---", "", issue.disclaimer, ""])
    return "\n".join(lines)

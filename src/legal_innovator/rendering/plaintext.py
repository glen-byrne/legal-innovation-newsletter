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
    for index, story in enumerate(issue.stories, start=1):
        lines.extend(
            [
                f"{index}. {story.headline}",
                f"Date: {story.date.isoformat()}",
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

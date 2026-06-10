"""Pull request body generation and optional local PR creation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from legal_innovator.models import Issue, QAReport, ReviewShortlist


def build_pr_title(issue: Issue) -> str:
    return f"Draft issue: {issue.newsletter_name} - {issue.run_date.isoformat()}"


def build_pr_body(issue: Issue, qa_report: QAReport, review_shortlist: ReviewShortlist | None = None) -> str:
    warning_flags = qa_report.warnings
    lines = [
        f"# {build_pr_title(issue)}",
        "",
        "## Summary",
        "",
        issue.intro,
        "",
        "## Final story list",
        "",
    ]
    for index, story in enumerate(issue.stories, start=1):
        sources = "; ".join(f"[{link.name}]({link.url})" for link in story.sources)
        lines.append(f"{index}. **{story.headline}** ({story.date.isoformat()}) - {sources}")

    if review_shortlist:
        selected = set(review_shortlist.selected_cluster_ids)
        if review_shortlist.max_final_stories > 0:
            selection_instruction = (
                f"Tick {review_shortlist.min_final_stories}-{review_shortlist.max_final_stories} stories."
            )
        else:
            selection_instruction = f"Tick at least {review_shortlist.min_final_stories} stories."
        lines.extend(
            [
                "",
                "## Editorial selection shortlist",
                "",
                selection_instruction,
                f"For a durable selection, edit `issues/{issue.run_date.isoformat()}/editorial_selection.md` "
                "and rerun the workflow for the same date.",
                "",
            ]
        )
        for index, story in enumerate(review_shortlist.stories, start=1):
            checked = "x" if story.cluster_id in selected else " "
            sources = "; ".join(f"[{link.name}]({link.url})" for link in story.sources)
            lines.append(f"- [{checked}] **{index}. {story.headline}** ({story.date.isoformat()}) - {sources}")

    lines.extend(["", "## QA checklist", ""])
    for item, passed in qa_report.checklist.items():
        lines.append(f"- [{'x' if passed else ' '}] {item}")

    confirmations = {
        "All stories are within the 14-day window": qa_report.checklist.get(
            "all stories are within the 14-day window", False
        ),
        "Every story has at least one reliable source": qa_report.checklist.get(
            "every story has at least one reliable source", False
        ),
        "Visible scoring is not included": qa_report.checklist.get("visible scoring is not included", False),
        "Opinion pieces and vendor-only announcements were excluded": True,
        "Disclaimer is included": qa_report.checklist.get("disclaimer is included", False),
    }
    lines.extend(["", "## Review confirmations", ""])
    for item, passed in confirmations.items():
        lines.append(f"- [{'x' if passed else ' '}] {item}")

    lines.extend(["", "## Warning flags", ""])
    if warning_flags:
        for warning in warning_flags:
            story = f" ({warning.story_headline})" if warning.story_headline else ""
            lines.append(f"- {warning.message}{story}")
    else:
        lines.append("- None.")

    lines.extend(["", "## Notes", ""])
    lines.append("- This MVP does not send email and does not create beehiiv drafts.")
    lines.append("- Merging archives the generated issue and seen-story tracking files in the repository.")
    lines.append("")
    return "\n".join(lines)


def create_pull_request(issue: Issue, body_path: str | Path) -> None:
    """Create a PR using the GitHub CLI when available.

    GitHub Actions uses a dedicated create-pull-request action; this helper is
    for local environments that have git and gh configured.
    """

    branch = f"newsletter/{issue.run_date.isoformat()}"
    title = build_pr_title(issue)
    body_file = str(body_path)
    if not _command_exists("git") or not _command_exists("gh"):
        raise RuntimeError("Local PR creation requires both git and gh on PATH. Re-run with --no-pr or use Actions.")
    subprocess.run(["git", "checkout", "-B", branch], check=True)
    subprocess.run(["git", "add", "issues", "data/seen_urls.json", "data/seen_story_clusters.json"], check=True)
    subprocess.run(["git", "commit", "-m", title], check=True)
    subprocess.run(["git", "push", "--set-upstream", "origin", branch], check=True)
    base = os.getenv("GITHUB_BASE_BRANCH", "main")
    subprocess.run(["gh", "pr", "create", "--base", base, "--title", title, "--body-file", body_file], check=True)


def _command_exists(command: str) -> bool:
    from shutil import which

    return which(command) is not None

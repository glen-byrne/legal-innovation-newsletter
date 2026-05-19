"""Deterministic and AI-assisted QA checks."""

from __future__ import annotations

from pydantic import BaseModel, Field

from legal_innovator.ai import StructuredAIClient
from legal_innovator.config import RunWindow, Settings
from legal_innovator.errors import ErrorStage, StageError
from legal_innovator.models import Issue, QAFinding, QAReport, StoryCluster


class AIQAFinding(BaseModel):
    severity: str
    message: str
    story_headline: str | None = None


class AIQAResult(BaseModel):
    findings: list[AIQAFinding] = Field(default_factory=list)


QA_SYSTEM = """You are a factual QA editor for an executive legal innovation newsletter.
Return JSON only. Check whether story summaries and why-it-matters statements are supported by the supplied source snippets/metadata/permitted text.
Flag unsupported factual claims, paywall overreach, legal advice phrasing, hype, or missing caveats.
"""


def run_qa(
    issue: Issue,
    window: RunWindow,
    settings: Settings,
    rendered: dict[str, str],
    clusters: list[StoryCluster] | None = None,
    stage_errors: list[StageError] | None = None,
    *,
    ai_client: StructuredAIClient | None = None,
) -> QAReport:
    findings: list[QAFinding] = []
    checklist = _deterministic_checklist(issue, window, rendered)
    for key, passed in checklist.items():
        if not passed:
            findings.append(QAFinding(severity="error", message=f"Checklist failed: {key}"))

    if len(issue.stories) < settings.min_final_stories:
        findings.append(
            QAFinding(
                severity="warning",
                message=(
                    f"Only {len(issue.stories)} qualified stories were found; "
                    f"target minimum is {settings.min_final_stories}."
                ),
            )
        )

    for story in issue.stories:
        for note in story.qa_notes:
            findings.append(QAFinding(severity="warning", message=note, story_headline=story.headline))

    if clusters and not settings.dry_run_no_ai:
        ai_findings = _run_ai_qa(issue, clusters, settings, ai_client)
        findings.extend(ai_findings)

    stage_error_strings = [error.as_markdown() for error in stage_errors or []]
    passed = not any(finding.severity == "error" for finding in findings)
    return QAReport(
        issue_date=issue.run_date,
        passed=passed,
        findings=findings,
        stage_errors=stage_error_strings,
        checklist=checklist,
    )


def render_qa_report(report: QAReport) -> str:
    lines = [
        f"# QA report: {report.issue_date.isoformat()}",
        "",
        f"**Status:** {'Passed' if report.passed else 'Needs attention'}",
        "",
        "## Checklist",
        "",
    ]
    for key, passed in report.checklist.items():
        lines.append(f"- [{'x' if passed else ' '}] {key}")
    lines.extend(["", "## Findings", ""])
    if report.findings:
        for finding in report.findings:
            story = f" ({finding.story_headline})" if finding.story_headline else ""
            lines.append(f"- **{finding.severity}**{story}: {finding.message}")
    else:
        lines.append("- No findings.")
    lines.extend(["", "## Stage errors and warnings", ""])
    if report.stage_errors:
        lines.extend(f"- {error}" for error in report.stage_errors)
    else:
        lines.append("- None recorded.")
    lines.append("")
    return "\n".join(lines)


def _deterministic_checklist(issue: Issue, window: RunWindow, rendered: dict[str, str]) -> dict[str, bool]:
    rendered_text = "\n".join(rendered.values()).lower()
    return {
        "issue has no more than 12 stories": len(issue.stories) <= 12,
        "issue has at least one story": len(issue.stories) > 0,
        "all stories are within the 14-day window": all(
            window.start_at.date() <= story.date <= window.end_at.date() for story in issue.stories
        ),
        "every story has at least one reliable source": all(len(story.sources) >= 1 for story in issue.stories),
        "no story has more than 3 source links": all(len(story.sources) <= 3 for story in issue.stories),
        "visible scoring is not included": _visible_scores_absent(issue, rendered_text),
        "disclaimer is included": issue.disclaimer in rendered.get("html", "")
        and issue.disclaimer in rendered.get("markdown", "")
        and issue.disclaimer in rendered.get("plaintext", ""),
        "all rendered formats are non-empty": all(bool(value.strip()) for value in rendered.values()),
    }


def _visible_scores_absent(issue: Issue, rendered_text: str) -> bool:
    forbidden_labels = ("internal score", "relevance score", "score_breakdown", "score breakdown")
    if any(label in rendered_text for label in forbidden_labels):
        return False
    for story in issue.stories:
        if story.score and (str(story.score).lower() in rendered_text or f"{story.score:.3f}" in rendered_text):
            return False
    return True


def _run_ai_qa(
    issue: Issue,
    clusters: list[StoryCluster],
    settings: Settings,
    ai_client: StructuredAIClient | None,
) -> list[QAFinding]:
    try:
        client = ai_client or StructuredAIClient(settings)
        result = client.complete_json(
            schema=AIQAResult,
            system=QA_SYSTEM,
            user=_qa_prompt(issue, clusters),
            high_quality=True,
        )
    except Exception as exc:  # noqa: BLE001
        return [QAFinding(severity="warning", message=f"AI factual QA failed: {exc}")]
    findings: list[QAFinding] = []
    for item in result.findings:
        severity = item.severity if item.severity in {"info", "warning", "error"} else "warning"
        findings.append(QAFinding(severity=severity, message=item.message, story_headline=item.story_headline))
    return findings


def _qa_prompt(issue: Issue, clusters: list[StoryCluster]) -> str:
    cluster_map = {cluster.cluster_id: cluster for cluster in clusters}
    lines = ["Check this issue against supplied source context."]
    for story in issue.stories:
        lines.append(
            f"\nStory: {story.headline}\nSummary: {story.summary}\nWhy: {story.why_it_matters}\nSources: "
            + "; ".join(f"{link.name} {link.url}" for link in story.sources)
        )
        cluster = cluster_map.get(story.cluster_id)
        if cluster:
            for article in cluster.articles[:3]:
                lines.append(f"Source context from {article.source_name}:\n{article.safe_context(1500)}")
    return "\n".join(lines)

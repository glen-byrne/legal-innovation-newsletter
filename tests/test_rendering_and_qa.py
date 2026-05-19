from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from legal_innovator.archive import rendered_outputs
from legal_innovator.config import Settings
from legal_innovator.models import Issue, RankedStory, ScoreBreakdown, SourceLink
from legal_innovator.qa import run_qa
from legal_innovator.summarisation import summarise_issue


def make_issue(story_count: int = 8) -> Issue:
    tz = ZoneInfo("Europe/Dublin")
    run_at = datetime(2026, 5, 19, 12, 0, tzinfo=tz)
    stories = []
    for index in range(story_count):
        stories.append(
            RankedStory(
                headline=f"Legal AI development {index + 1}",
                date=(run_at - timedelta(days=index + 1)).date(),
                canonical_url=f"https://example.com/story-{index}",
                sources=[SourceLink(name="Example Legal News", url=f"https://example.com/story-{index}")],
                source_names=["Example Legal News"],
                source_types=["legal_tech_media"],
                summary="A reliable source reported a legal innovation development.",
                why_it_matters="Legal teams may need to consider operational and risk implications.",
                score=99.9,
                score_breakdown=ScoreBreakdown(region=25),
                cluster_id=f"cluster-{index}",
            )
        )
    return Issue(
        newsletter_name="The Irish Legal Innovator",
        run_date=run_at.date(),
        generated_at=run_at,
        window_start=(run_at - timedelta(days=14)).date(),
        window_end=run_at.date(),
        intro="This fortnight saw several legal innovation developments with practical implications for legal teams.",
        stories=stories,
    )


def test_rendered_outputs_exclude_internal_scores() -> None:
    issue = make_issue()
    outputs = rendered_outputs(issue)
    visible = "\n".join(outputs.values()).lower()
    assert "score" not in visible
    assert "99.9" not in visible
    assert issue.disclaimer in outputs["html"]
    assert issue.disclaimer in outputs["markdown"]
    assert issue.disclaimer in outputs["plaintext"]


def test_qa_acceptance_checks_pass_for_valid_issue() -> None:
    issue = make_issue()
    settings = Settings(dry_run_no_ai=True)
    run_at = datetime(2026, 5, 19, 12, 0, tzinfo=ZoneInfo("Europe/Dublin"))
    window = type("Window", (), {"start_at": run_at - timedelta(days=14), "end_at": run_at})()
    report = run_qa(issue, window, settings, rendered_outputs(issue))
    assert report.passed
    assert report.checklist["all stories are within the 14-day window"]
    assert report.checklist["no story has more than 3 source links"]


def test_qa_flags_story_outside_window() -> None:
    issue = make_issue()
    issue.stories[0].date = issue.window_start - timedelta(days=1)
    settings = Settings(dry_run_no_ai=True)
    run_at = datetime(2026, 5, 19, 12, 0, tzinfo=ZoneInfo("Europe/Dublin"))
    window = type("Window", (), {"start_at": run_at - timedelta(days=14), "end_at": run_at})()
    report = run_qa(issue, window, settings, rendered_outputs(issue))
    assert not report.passed
    assert not report.checklist["all stories are within the 14-day window"]


def test_empty_issue_is_plainly_labelled_without_ai_intro() -> None:
    settings = Settings(dry_run_no_ai=False, openai_api_key="test", openai_model_fast="fast", openai_model_high_quality="hq")
    intro, stories, errors = summarise_issue([], [], settings)
    assert not stories
    assert not errors
    assert "No qualified stories" in intro

    tz = ZoneInfo("Europe/Dublin")
    run_at = datetime(2026, 5, 19, 12, 0, tzinfo=tz)
    issue = Issue(
        newsletter_name="The Irish Legal Innovator",
        run_date=run_at.date(),
        generated_at=run_at,
        window_start=(run_at - timedelta(days=14)).date(),
        window_end=run_at.date(),
        intro=intro,
        stories=[],
    )
    outputs = rendered_outputs(issue)
    assert "No qualified stories" in outputs["plaintext"]
    assert "No Qualified Stories" in outputs["markdown"]
    assert "No Qualified Stories" in outputs["html"]

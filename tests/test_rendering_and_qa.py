from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from legal_innovator.archive import rendered_outputs
from legal_innovator.config import Settings
from legal_innovator.models import Issue, RankedStory, ScoreBreakdown, SourceDiagnostic, SourceLink
from legal_innovator.qa import render_qa_report, run_qa
from legal_innovator.summarisation import SummaryBatch, StorySummary, summarise_issue


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
                region_tags=["Ireland"] if index % 2 == 0 else ["United Kingdom", "European Union"],
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
        newsletter_name="The Legal Edge Ireland",
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


def test_html_template_uses_brand_identity_palette() -> None:
    issue = make_issue()
    html = rendered_outputs(issue)["html"]

    assert "#1E3B2E" in html
    assert "#8B7966" in html
    assert "#5A3E2B" in html
    assert "#DCCBB2" in html
    assert "#F5F1EA" in html
    assert "The latest on legal innovation, technology, AI and design for the Irish legal sector." in html
    assert ">LEI<" not in html
    assert "data:image/png;base64" in html
    assert "The Legal Edge" in html
    assert "Ireland" in html
    assert "Innovator</h1>" not in html
    assert "Est. 2024" not in html
    assert "Issue date:" not in html
    assert "Issue: 19 May 2026" in html
    assert "18 May 2026" in html
    assert "Click here to subscribe" in html
    assert "In today's issue:" in html
    assert "Impact:" in html
    assert "mailto:legal.innovation.news@gmail.com" in html
    assert "What do you think? Provide feedback" in html
    assert "Unsubscribe" in html


def test_rendered_outputs_include_visible_region_tags() -> None:
    issue = make_issue(story_count=2)
    outputs = rendered_outputs(issue)

    assert '<span class="region-tag">Ireland</span>' in outputs["html"]
    assert '<span class="region-tag">United Kingdom</span>' in outputs["html"]
    assert '<span class="region-tag">European Union</span>' in outputs["html"]
    assert "**Regions:** Ireland" in outputs["markdown"]
    assert "Regions: United Kingdom, European Union" in outputs["plaintext"]


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
        newsletter_name="The Legal Edge Ireland",
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


def test_qa_report_renders_source_diagnostics() -> None:
    issue = make_issue()
    settings = Settings(dry_run_no_ai=True)
    run_at = datetime(2026, 5, 19, 12, 0, tzinfo=ZoneInfo("Europe/Dublin"))
    window = type("Window", (), {"start_at": run_at - timedelta(days=14), "end_at": run_at})()
    report = run_qa(
        issue,
        window,
        settings,
        rendered_outputs(issue),
        source_diagnostics=[
            SourceDiagnostic(
                name="Irish Tech News",
                kind="rss",
                url_or_query="https://irishtechnews.ie/feed/",
                candidates_found=3,
                status="ok",
            ),
            SourceDiagnostic(
                name="Law.com Legaltech News",
                kind="webpage",
                url_or_query="https://www.law.com/legaltechnews/",
                candidates_found=0,
                status="error",
                notes=["403 Forbidden"],
            ),
        ],
    )

    markdown = render_qa_report(report)

    assert "## Source diagnostics" in markdown
    assert "Irish Tech News" in markdown
    assert "Law.com Legaltech News" in markdown
    assert "403 Forbidden" in markdown


def test_summarisation_matches_by_order_when_cluster_ids_differ() -> None:
    class FakeAI:
        def complete_json(self, **kwargs):
            return SummaryBatch(
                intro="A concise executive briefing intro.",
                stories=[
                    StorySummary(
                        cluster_id="changed-id",
                        headline="Updated headline",
                        summary="A neutral generated summary.",
                        why_it_matters="It gives legal teams a practical signal to monitor.",
                    )
                ],
            )

    issue = make_issue(story_count=1)
    settings = Settings(openai_api_key="test", openai_model_fast="fast", openai_model_high_quality="hq")
    intro, stories, errors = summarise_issue(issue.stories, [], settings, ai_client=FakeAI())

    assert not errors
    assert intro == "A concise executive briefing intro."
    assert stories[0].headline == "Updated headline"
    assert stories[0].summary == "A neutral generated summary."
    assert not stories[0].qa_notes

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from legal_innovator.archive import write_issue_outputs
from legal_innovator.models import ExtractedArticle, ReviewShortlist
from legal_innovator.pr import build_pr_body
from legal_innovator.qa import QAReport
from tests.test_rendering_and_qa import make_issue


def test_extracted_article_model_dump_excludes_full_text() -> None:
    article = ExtractedArticle(
        title="Irish courts digital transformation update",
        url="https://example.com/a",
        source_name="Example",
        source_url="https://example.com",
        published_at=datetime(2026, 5, 18, tzinfo=ZoneInfo("Europe/Dublin")),
        article_text="FULL ARTICLE TEXT SHOULD NOT BE ARCHIVED",
    )
    dumped = article.model_dump(mode="json")
    assert "article_text" not in dumped


def test_issue_json_does_not_store_full_article_text(tmp_path: Path) -> None:
    issue = make_issue()
    write_issue_outputs(issue, tmp_path, qa_report_markdown="# QA\n")
    data = json.loads((tmp_path / "issue.json").read_text(encoding="utf-8"))
    assert data["stories"]
    assert "FULL ARTICLE TEXT" not in json.dumps(data)


def test_write_issue_outputs_includes_review_shortlist_and_selection(tmp_path: Path) -> None:
    issue = make_issue()
    shortlist = ReviewShortlist(
        newsletter_name=issue.newsletter_name,
        run_date=issue.run_date,
        generated_at=issue.generated_at,
        window_start=issue.window_start,
        window_end=issue.window_end,
        min_final_stories=8,
        max_final_stories=12,
        selected_cluster_ids=[story.cluster_id for story in issue.stories],
        stories=issue.stories,
    )

    write_issue_outputs(
        issue,
        tmp_path,
        qa_report_markdown="# QA\n",
        review_shortlist=shortlist,
        selection_markdown="# Selection\n",
    )

    assert (tmp_path / "review_shortlist.json").exists()
    assert (tmp_path / "editorial_selection.md").exists()


def test_pr_body_contains_required_review_sections() -> None:
    issue = make_issue()
    report = QAReport(
        issue_date=issue.run_date,
        passed=True,
        checklist={
            "all stories are within the 14-day window": True,
            "every story has at least one reliable source": True,
            "visible scoring is not included": True,
            "disclaimer is included": True,
        },
    )
    shortlist = ReviewShortlist(
        newsletter_name=issue.newsletter_name,
        run_date=issue.run_date,
        generated_at=issue.generated_at,
        window_start=issue.window_start,
        window_end=issue.window_end,
        min_final_stories=8,
        max_final_stories=12,
        selected_cluster_ids=[issue.stories[0].cluster_id],
        stories=issue.stories,
    )
    body = build_pr_body(issue, report, shortlist)
    assert "Final story list" in body
    assert "Editorial selection shortlist" in body
    assert "- [x]" in body
    assert "- [ ]" in body
    assert "[Ireland]" in body
    assert "[United Kingdom, European Union]" in body
    assert "QA checklist" in body
    assert "Opinion pieces and vendor-only announcements were excluded" in body
    assert "does not send email" in body

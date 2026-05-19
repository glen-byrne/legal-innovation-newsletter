from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from legal_innovator.archive import write_issue_outputs
from legal_innovator.models import ExtractedArticle
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
    body = build_pr_body(issue, report)
    assert "Final story list" in body
    assert "QA checklist" in body
    assert "Opinion pieces and vendor-only announcements were excluded" in body
    assert "does not send email" in body

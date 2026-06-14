from __future__ import annotations

import json

import pytest

from legal_innovator.dashboard.app import DashboardSettings, is_authenticated
from legal_innovator.dashboard.github import GitHubSettings, candidate_count
from legal_innovator.dashboard.selection import build_editorial_selection_markdown, validate_selection_count
from legal_innovator.selection import parse_selected_cluster_ids
from tests.test_rendering_and_qa import make_issue


def make_shortlist() -> dict:
    return {
        "newsletter_name": "The Legal Edge Ireland",
        "run_date": "2026-06-10",
        "min_final_stories": 1,
        "max_final_stories": 2,
        "selected_cluster_ids": ["story-1"],
        "stories": [
            {
                "cluster_id": "story-1",
                "headline": "First story",
                "date": "2026-06-10",
                "region_tags": ["Ireland"],
                "sources": [{"name": "Example Source", "url": "https://example.com/one"}],
            },
            {
                "cluster_id": "story-2",
                "headline": "Second story",
                "date": "2026-06-09",
                "region_tags": ["United Kingdom", "European Union"],
                "sources": [{"name": "Example Source", "url": "https://example.com/two"}],
            },
        ],
    }


def test_dashboard_selection_markdown_matches_existing_parser(tmp_path) -> None:
    markdown = build_editorial_selection_markdown(make_shortlist(), ["story-2"])
    path = tmp_path / "editorial_selection.md"
    path.write_text(markdown, encoding="utf-8")

    assert parse_selected_cluster_ids(path) == ["story-2"]
    assert "<!-- story:story-1 -->" in markdown
    assert "<!-- story:story-2 -->" in markdown
    assert "Regions: Ireland" in markdown
    assert "Regions: United Kingdom, European Union" in markdown


def test_dashboard_selection_markdown_preserves_selected_order(tmp_path) -> None:
    markdown = build_editorial_selection_markdown(make_shortlist(), ["story-2", "story-1"])
    path = tmp_path / "editorial_selection.md"
    path.write_text(markdown, encoding="utf-8")

    assert parse_selected_cluster_ids(path) == ["story-2", "story-1"]
    assert markdown.index("Second story") < markdown.index("First story")


def test_dashboard_selection_count_validation() -> None:
    assert validate_selection_count([], 1, 2) == "Select at least 1 stories. You selected 0."
    assert validate_selection_count(["one", "two", "three"], 1, 2) == "Select no more than 2 stories. You selected 3."
    assert validate_selection_count(["one", "two"], 1, 2) is None
    assert validate_selection_count(["one", "two", "three"], 1, 0) is None


def test_candidate_count_handles_missing_candidates() -> None:
    assert candidate_count({"candidates": [{}, {}]}) == 2
    assert candidate_count({}) == 0


def test_scan_prompt_text_extracts_fenced_prompt(monkeypatch, tmp_path) -> None:
    from legal_innovator.dashboard.app import _scan_prompt_text

    monkeypatch.chdir(tmp_path)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "codex-news-scan-prompt.md").write_text(
        "Intro\n\n```text\nPrompt body\nSecond line\n```\n",
        encoding="utf-8",
    )

    assert _scan_prompt_text() == "Prompt body\nSecond line"


def test_dashboard_login_page_renders(monkeypatch) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from legal_innovator.dashboard.app import app

    monkeypatch.setenv("DASHBOARD_GITHUB_REPOSITORY", "glen-byrne/legal-innovation-newsletter")
    monkeypatch.setenv("DASHBOARD_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "test-password")
    monkeypatch.setenv("DASHBOARD_COOKIE_SECURE", "false")

    client = fastapi_testclient.TestClient(app)
    response = client.get("/login")

    assert response.status_code == 200
    assert "Sign in" in response.text


def test_dashboard_no_auth_overrides_password() -> None:
    settings = DashboardSettings(
        github=GitHubSettings(
            repository="glen-byrne/legal-innovation-newsletter",
            token="test-token",
        ),
        password="old-password",
        secret_key="test-secret",
        allow_no_auth=True,
    )

    assert is_authenticated(request=object(), settings=settings) is True


def test_dashboard_local_generation_from_candidates(monkeypatch, tmp_path) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from legal_innovator.dashboard.app import app

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DASHBOARD_GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("DASHBOARD_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    monkeypatch.setenv("DASHBOARD_ALLOW_NO_AUTH", "true")
    monkeypatch.setenv("DASHBOARD_COOKIE_SECURE", "false")
    issue_dir = tmp_path / "issues" / "2026-06-10"
    issue_dir.mkdir(parents=True)
    candidates = [_candidate(index) for index in range(1, 9)]
    candidates[1]["region"] = "UK/EU"
    (issue_dir / "candidates.json").write_text(json.dumps({"candidates": candidates}), encoding="utf-8")

    client = fastapi_testclient.TestClient(app)
    index_response = client.get("/")
    assert index_response.status_code == 200
    assert "2026-06-10" in index_response.text

    review_response = client.get("/issues/2026-06-10")
    assert review_response.status_code == 200
    assert "Example factual basis 1." in review_response.text
    assert "Ireland" in review_response.text
    assert "Drag story to reorder" in review_response.text
    assert "data-drag-handle" in review_response.text
    assert "data-remove-region" in review_response.text
    assert "Why it matters:" in review_response.text
    assert "Example legal-sector relevance 1." in review_response.text

    selected_ids = [candidate["id"] for candidate in reversed(candidates)]
    form_data = {
        "selected": selected_ids,
        "region_tag_story": [candidate["id"] for candidate in candidates],
    }
    for candidate in candidates:
        story_id = str(candidate["id"])
        form_data[f"region_tags__{story_id}"] = ["United Kingdom"] if story_id == candidates[1]["id"] else ["Ireland"]
    response = client.post(
        "/issues/2026-06-10/generate-html",
        data=form_data,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert (issue_dir / "issue.html").exists()
    assert (issue_dir / "editorial_selection.md").exists()
    html = (issue_dir / "issue.html").read_text(encoding="utf-8")
    assert "Story 1" in html
    assert "This issue leads with Story 8, Story 7, and Story 6." in html
    assert "Legal innovation developments affecting" not in html
    assert html.index("Story 8") < html.index("Story 1")
    assert '<span class="region-tag">Ireland</span>' in html
    assert '<span class="region-tag">United Kingdom</span>' in html
    assert '<span class="region-tag">European Union</span>' not in html
    assert parse_selected_cluster_ids(issue_dir / "editorial_selection.md") == selected_ids


def test_dashboard_generate_html_get_redirects(monkeypatch, tmp_path) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from legal_innovator.dashboard.app import app

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DASHBOARD_GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("DASHBOARD_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    monkeypatch.setenv("DASHBOARD_ALLOW_NO_AUTH", "true")

    client = fastapi_testclient.TestClient(app)
    response = client.get("/issues/2026-06-10/generate-html", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/issues/2026-06-10"


def test_dashboard_generated_html_shows_brevo_button_when_configured(monkeypatch, tmp_path) -> None:
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from legal_innovator.archive import write_issue_outputs
    from legal_innovator.dashboard.app import app

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DASHBOARD_ALLOW_NO_AUTH", "true")
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "sender@example.com")
    monkeypatch.setenv("BREVO_LIST_IDS", "42")
    write_issue_outputs(make_issue(), tmp_path / "issues" / "2026-05-19", qa_report_markdown="# QA\n")

    client = fastapi_testclient.TestClient(app)
    response = client.get("/issues/2026-05-19/html")

    assert response.status_code == 200
    assert "Create Brevo draft" in response.text
    assert "Open Brevo" in response.text


def _candidate(index: int) -> dict[str, object]:
    return {
        "id": f"ILIN-2026-06-10-{index:03d}",
        "headline": f"Story {index}",
        "published_date": "2026-06-01",
        "source_name": "Example Source",
        "source_url": f"https://example.com/story-{index}",
        "event_type": "legal_ai_adoption",
        "source_origin": "confirmed_reporting",
        "region": "Ireland",
        "factual_basis": f"Example factual basis {index}.",
        "legal_sector_relevance_note": f"Example legal-sector relevance {index}.",
        "duplicate_group": "none",
        "warning_flags": [],
        "selected": True,
    }

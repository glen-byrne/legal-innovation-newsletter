from __future__ import annotations

import pytest

from legal_innovator.dashboard.app import DashboardSettings, is_authenticated
from legal_innovator.dashboard.github import GitHubSettings, candidate_count
from legal_innovator.dashboard.selection import build_editorial_selection_markdown, validate_selection_count
from legal_innovator.selection import parse_selected_cluster_ids


def make_shortlist() -> dict:
    return {
        "newsletter_name": "The Irish Legal Innovator",
        "run_date": "2026-06-10",
        "min_final_stories": 1,
        "max_final_stories": 2,
        "selected_cluster_ids": ["story-1"],
        "stories": [
            {
                "cluster_id": "story-1",
                "headline": "First story",
                "date": "2026-06-10",
                "sources": [{"name": "Example Source", "url": "https://example.com/one"}],
            },
            {
                "cluster_id": "story-2",
                "headline": "Second story",
                "date": "2026-06-09",
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


def test_dashboard_selection_count_validation() -> None:
    assert validate_selection_count([], 1, 2) == "Select at least 1 stories. You selected 0."
    assert validate_selection_count(["one", "two", "three"], 1, 2) == "Select no more than 2 stories. You selected 3."
    assert validate_selection_count(["one", "two"], 1, 2) is None


def test_candidate_count_handles_missing_candidates() -> None:
    assert candidate_count({"candidates": [{}, {}]}) == 2
    assert candidate_count({}) == 0


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

from __future__ import annotations

import json

import httpx

from legal_innovator.publishing import BrevoPublisher, BrevoSettings, load_brevo_settings_from_env
from tests.test_rendering_and_qa import make_issue


def test_brevo_publisher_creates_draft_campaign_payload() -> None:
    issue = make_issue(story_count=1)
    seen_payload: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_payload
        assert request.url == "https://api.brevo.com/v3/emailCampaigns"
        assert request.headers["api-key"] == "test-key"
        seen_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(201, json={"id": 123})

    publisher = BrevoPublisher(
        BrevoSettings(
            api_key="test-key",
            sender_name="The Legal Edge Ireland",
            sender_email="sender@example.com",
            list_ids=(42,),
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    draft_id = publisher.create_draft(issue, "<html>newsletter</html>", "", "Plain text")

    assert draft_id == "123"
    assert seen_payload["name"] == "The Legal Edge Ireland - 2026-05-19"
    assert seen_payload["subject"] == "The Legal Edge Ireland - 19 May 2026"
    assert seen_payload["sender"] == {"name": "The Legal Edge Ireland", "email": "sender@example.com"}
    assert seen_payload["recipients"] == {"listIds": [42]}
    assert seen_payload["htmlContent"] == "<html>newsletter</html>"
    assert seen_payload["previewText"].startswith("This fortnight saw")


def test_brevo_settings_require_api_sender_and_list(monkeypatch) -> None:
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("BREVO_SENDER_NAME", "The Legal Edge Ireland")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "sender@example.com")
    monkeypatch.setenv("BREVO_LIST_IDS", "42, 43")

    settings = load_brevo_settings_from_env()

    assert settings is not None
    assert settings.list_ids == (42, 43)
    assert settings.reply_to == "sender@example.com"


def test_brevo_settings_are_absent_until_complete(monkeypatch) -> None:
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("BREVO_SENDER_EMAIL", raising=False)
    monkeypatch.delenv("BREVO_SENDER_ID", raising=False)
    monkeypatch.delenv("BREVO_LIST_IDS", raising=False)

    assert load_brevo_settings_from_env() is None

    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "sender@example.com")
    assert load_brevo_settings_from_env() is None

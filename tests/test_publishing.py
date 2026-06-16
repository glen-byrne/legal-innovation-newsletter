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
    assert "tag" not in seen_payload


def test_brevo_publisher_retries_without_campaign_tag_when_brevo_rejects_it() -> None:
    issue = make_issue(story_count=1)
    seen_payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(json.loads(request.content.decode("utf-8")))
        if len(seen_payloads) == 1:
            return httpx.Response(405, json={"message": "You are not allowed to avail tag option for your campaign"})
        return httpx.Response(201, json={"id": 456})

    publisher = BrevoPublisher(
        BrevoSettings(
            api_key="test-key",
            sender_name="The Legal Edge Ireland",
            sender_email="sender@example.com",
            list_ids=(42,),
            campaign_tag="legal-edge-ireland",
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    draft_id = publisher.create_draft(issue, "<html>newsletter</html>", "", "Plain text")

    assert draft_id == "456"
    assert seen_payloads[0]["tag"] == "legal-edge-ireland"
    assert "tag" not in seen_payloads[1]


def test_brevo_publisher_resolves_named_lists_before_creating_campaign() -> None:
    issue = make_issue(story_count=1)
    seen_payload: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_payload
        if request.url.path == "/v3/contacts/lists":
            return httpx.Response(
                200,
                json={
                    "lists": [
                        {"id": 7, "name": "test-list"},
                        {"id": 8, "name": "the-legal-edge-IE"},
                    ]
                },
            )
        assert request.url == "https://api.brevo.com/v3/emailCampaigns"
        seen_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(201, json={"id": 789})

    publisher = BrevoPublisher(
        BrevoSettings(
            api_key="test-key",
            sender_name="The Legal Edge Ireland",
            sender_email="sender@example.com",
            list_names=("test-list", "the-legal-edge-IE"),
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    draft_id = publisher.create_draft(issue, "<html>newsletter</html>", "", "Plain text")

    assert draft_id == "789"
    assert seen_payload["recipients"] == {"listIds": [7, 8]}


def test_brevo_settings_require_api_sender_and_list(monkeypatch) -> None:
    monkeypatch.delenv("BREVO_REPLY_TO", raising=False)
    monkeypatch.delenv("BREVO_CAMPAIGN_TAG", raising=False)
    monkeypatch.delenv("BREVO_LIST_NAMES", raising=False)
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("BREVO_SENDER_NAME", "The Legal Edge Ireland")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "sender@example.com")
    monkeypatch.setenv("BREVO_LIST_IDS", "42, 43")

    settings = load_brevo_settings_from_env()

    assert settings is not None
    assert settings.list_ids == (42, 43)
    assert settings.reply_to == "sender@example.com"
    assert settings.campaign_tag is None


def test_brevo_settings_can_use_list_names_instead_of_ids(monkeypatch) -> None:
    monkeypatch.delenv("BREVO_REPLY_TO", raising=False)
    monkeypatch.delenv("BREVO_CAMPAIGN_TAG", raising=False)
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("BREVO_SENDER_NAME", "The Legal Edge Ireland")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "sender@example.com")
    monkeypatch.setenv("BREVO_LIST_IDS", "999")
    monkeypatch.setenv("BREVO_LIST_NAMES", "test-list, the-legal-edge-IE")

    settings = load_brevo_settings_from_env()

    assert settings is not None
    assert settings.list_ids == ()
    assert settings.list_names == ("test-list", "the-legal-edge-IE")


def test_brevo_settings_are_absent_until_complete(monkeypatch) -> None:
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("BREVO_SENDER_EMAIL", raising=False)
    monkeypatch.delenv("BREVO_SENDER_ID", raising=False)
    monkeypatch.delenv("BREVO_LIST_IDS", raising=False)
    monkeypatch.delenv("BREVO_LIST_NAMES", raising=False)

    assert load_brevo_settings_from_env() is None

    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "sender@example.com")
    assert load_brevo_settings_from_env() is None

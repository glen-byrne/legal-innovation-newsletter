"""Publisher adapter boundary.

Publishers create reviewable drafts in external newsletter platforms. They must
never send campaigns automatically.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from legal_innovator.archive import rendered_outputs
from legal_innovator.models import Issue


class Publisher(ABC):
    @abstractmethod
    def create_draft(self, issue: Issue, html: str, markdown: str, plaintext: str) -> str:
        """Create a draft and return a provider draft ID."""


class BeehiivPublisher(Publisher):
    def create_draft(self, issue: Issue, html: str, markdown: str, plaintext: str) -> str:
        raise NotImplementedError(
            "Beehiiv publishing is intentionally not implemented in the MVP. "
            "Add this after PR approval/merge workflow is defined."
        )


@dataclass(frozen=True)
class BrevoSettings:
    api_key: str
    sender_name: str
    sender_email: str | None = None
    sender_id: int | None = None
    list_ids: tuple[int, ...] = ()
    list_names: tuple[str, ...] = ()
    reply_to: str | None = None
    campaign_tag: str | None = None
    api_base_url: str = "https://api.brevo.com/v3"

    @property
    def is_configured(self) -> bool:
        return bool(
            self.api_key
            and self.sender_name
            and (self.sender_email or self.sender_id)
            and (self.list_ids or self.list_names)
        )


def load_brevo_settings_from_env() -> BrevoSettings | None:
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    if not api_key:
        return None
    sender_name = os.getenv("BREVO_SENDER_NAME", "The Legal Edge Ireland").strip()
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "").strip() or None
    sender_id = _parse_optional_int(os.getenv("BREVO_SENDER_ID"))
    if sender_email and sender_id is not None:
        raise ValueError("Set either BREVO_SENDER_EMAIL or BREVO_SENDER_ID, not both.")
    list_names = _parse_string_list(os.getenv("BREVO_LIST_NAMES", ""))
    list_ids = [] if list_names else _parse_int_list(os.getenv("BREVO_LIST_IDS", ""))
    settings = BrevoSettings(
        api_key=api_key,
        sender_name=sender_name,
        sender_email=sender_email,
        sender_id=sender_id,
        list_ids=tuple(list_ids),
        list_names=tuple(list_names),
        reply_to=os.getenv("BREVO_REPLY_TO", "").strip() or sender_email,
        campaign_tag=os.getenv("BREVO_CAMPAIGN_TAG", "").strip() or None,
        api_base_url=os.getenv("BREVO_API_BASE_URL", "https://api.brevo.com/v3").rstrip("/"),
    )
    if not settings.is_configured:
        return None
    return settings


class BrevoPublisher(Publisher):
    def __init__(self, settings: BrevoSettings, *, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client

    def create_draft(self, issue: Issue, html: str, markdown: str, plaintext: str) -> str:
        close_client = self.client is None
        client = self.client or httpx.Client(timeout=30)
        try:
            payload = self._campaign_payload(client, issue, html, plaintext)
            response = self._post_campaign(client, payload)
            if response.status_code == 405 and "tag" in payload and _brevo_rejected_tag(response):
                payload = {key: value for key, value in payload.items() if key != "tag"}
                response = self._post_campaign(client, payload)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        except httpx.HTTPStatusError as exc:
            message = _brevo_error_message(exc.response)
            raise RuntimeError(f"Brevo draft creation failed: {message}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Brevo draft creation failed: {exc}") from exc
        finally:
            if close_client:
                client.close()
        draft_id = data.get("id")
        if draft_id is None:
            raise RuntimeError("Brevo draft creation failed: response did not include a campaign ID.")
        return str(draft_id)

    def _post_campaign(self, client: httpx.Client, payload: dict[str, Any]) -> httpx.Response:
        return client.post(
            f"{self.settings.api_base_url}/emailCampaigns",
            headers=self._headers(content_type=True),
            json=payload,
        )

    def _campaign_payload(self, client: httpx.Client, issue: Issue, html: str, plaintext: str) -> dict[str, Any]:
        _ = plaintext
        sender: dict[str, Any] = {"name": self.settings.sender_name}
        if self.settings.sender_id is not None:
            sender["id"] = self.settings.sender_id
        elif self.settings.sender_email:
            sender["email"] = self.settings.sender_email
        payload: dict[str, Any] = {
            "name": f"{issue.newsletter_name} - {issue.run_date.isoformat()}",
            "sender": sender,
            "subject": f"{issue.newsletter_name} - {_display_date(issue.run_date)}",
            "previewText": _preview_text(issue),
            "htmlContent": html,
            "recipients": {"listIds": self._resolved_list_ids(client)},
        }
        if self.settings.campaign_tag:
            payload["tag"] = self.settings.campaign_tag
        if self.settings.reply_to:
            payload["replyTo"] = self.settings.reply_to
        return payload

    def _headers(self, *, content_type: bool = False) -> dict[str, str]:
        headers = {
            "accept": "application/json",
            "api-key": self.settings.api_key,
        }
        if content_type:
            headers["content-type"] = "application/json"
        return headers

    def _resolved_list_ids(self, client: httpx.Client) -> list[int]:
        if not self.settings.list_names:
            return list(self.settings.list_ids)
        name_map = self._brevo_lists_by_name(client)
        missing = [name for name in self.settings.list_names if name not in name_map]
        if missing:
            raise RuntimeError(f"Brevo list name not found: {', '.join(missing)}")
        resolved: list[int] = []
        seen: set[int] = set()
        for name in self.settings.list_names:
            list_id = name_map[name]
            if list_id in seen:
                continue
            resolved.append(list_id)
            seen.add(list_id)
        return resolved

    def _brevo_lists_by_name(self, client: httpx.Client) -> dict[str, int]:
        lists_by_name: dict[str, int] = {}
        limit = 50
        offset = 0
        while True:
            response = client.get(
                f"{self.settings.api_base_url}/contacts/lists",
                headers=self._headers(),
                params={"limit": limit, "offset": offset},
            )
            response.raise_for_status()
            data = response.json()
            lists = data.get("lists", []) if isinstance(data, dict) else []
            if not isinstance(lists, list):
                break
            for item in lists:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                try:
                    list_id = int(item.get("id"))
                except (TypeError, ValueError):
                    continue
                if name:
                    lists_by_name[name] = list_id
            if len(lists) < limit:
                break
            offset += limit
        return lists_by_name


def create_brevo_draft_from_issue_dir(issue_dir: str | os.PathLike[str]) -> str:
    from pathlib import Path

    path = Path(issue_dir)
    settings = load_brevo_settings_from_env()
    if settings is None:
        raise RuntimeError(
            "Brevo is not configured. Set BREVO_API_KEY, BREVO_SENDER_NAME, "
            "BREVO_SENDER_EMAIL or BREVO_SENDER_ID, and BREVO_LIST_NAMES or BREVO_LIST_IDS."
        )
    issue_json = path / "issue.json"
    if not issue_json.exists():
        raise RuntimeError(f"Cannot create Brevo draft because {issue_json} does not exist.")
    issue = Issue.model_validate_json(issue_json.read_text(encoding="utf-8"))
    outputs = rendered_outputs(issue)
    html_path = path / "issue.html"
    html = html_path.read_text(encoding="utf-8") if html_path.exists() else outputs["html"]
    return BrevoPublisher(settings).create_draft(issue, html, outputs["markdown"], outputs["plaintext"])


def _parse_optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return int(value.strip())


def _parse_int_list(value: str) -> list[int]:
    if not value.strip():
        return []
    items = value.replace(";", ",").split(",")
    return [int(item.strip()) for item in items if item.strip()]


def _parse_string_list(value: str) -> list[str]:
    if not value.strip():
        return []
    items = value.replace(";", ",").split(",")
    return [item.strip() for item in items if item.strip()]


def _display_date(value: date) -> str:
    return value.strftime("%d %B %Y").lstrip("0")


def _preview_text(issue: Issue) -> str:
    text = " ".join(issue.intro.split())
    if len(text) <= 140:
        return text
    return text[:140].rsplit(" ", 1)[0].rstrip(",;:") + "..."


def _brevo_error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:300]}"
    if isinstance(data, dict):
        message = data.get("message") or data.get("error") or data
        return f"HTTP {response.status_code}: {message}"
    return f"HTTP {response.status_code}: {data}"


def _brevo_rejected_tag(response: httpx.Response) -> bool:
    return "tag option" in _brevo_error_message(response).lower()

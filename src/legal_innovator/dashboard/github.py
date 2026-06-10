"""GitHub API adapter for the optional review dashboard."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx


ISSUE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class GitHubAPIError(RuntimeError):
    """Raised when GitHub returns an unexpected response."""


@dataclass(frozen=True)
class GitHubSettings:
    repository: str
    token: str
    base_branch: str = "main"
    workflow_file: str = "generate-newsletter.yml"
    api_base_url: str = "https://api.github.com"

    @property
    def web_base_url(self) -> str:
        return f"https://github.com/{self.repository}"


class GitHubClient:
    def __init__(self, settings: GitHubSettings) -> None:
        self.settings = settings

    async def list_issue_dates(self, ref: str | None = None) -> list[str]:
        entries = await self._request("GET", f"/repos/{self.settings.repository}/contents/issues", params={"ref": ref or self.settings.base_branch})
        if not isinstance(entries, list):
            return []
        dates = [entry["name"] for entry in entries if entry.get("type") == "dir" and ISSUE_DATE_RE.match(entry.get("name", ""))]
        return sorted(dates, reverse=True)

    async def branch_exists(self, branch: str) -> bool:
        try:
            await self._request("GET", f"/repos/{self.settings.repository}/branches/{branch}")
        except GitHubAPIError as exc:
            if "404" in str(exc):
                return False
            raise
        return True

    async def get_json(self, path: str, ref: str) -> tuple[dict[str, Any], str]:
        text, sha = await self.get_text(path, ref)
        data = json.loads(text)
        if not isinstance(data, dict):
            raise GitHubAPIError(f"{path} did not contain a JSON object")
        return data, sha

    async def get_text(self, path: str, ref: str) -> tuple[str, str]:
        data = await self._request("GET", f"/repos/{self.settings.repository}/contents/{path}", params={"ref": ref})
        if not isinstance(data, dict) or data.get("type") != "file":
            raise GitHubAPIError(f"{path} is not a file at {ref}")
        content = data.get("content", "")
        encoding = data.get("encoding")
        if encoding != "base64":
            raise GitHubAPIError(f"{path} used unsupported GitHub content encoding: {encoding}")
        return base64.b64decode(content).decode("utf-8"), data["sha"]

    async def put_text(self, path: str, branch: str, content: str, message: str) -> None:
        sha = None
        try:
            _, sha = await self.get_text(path, branch)
        except GitHubAPIError as exc:
            if "404" not in str(exc):
                raise
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        await self._request("PUT", f"/repos/{self.settings.repository}/contents/{path}", json=payload)

    async def dispatch_workflow(self, ref: str, inputs: dict[str, str]) -> None:
        payload = {"ref": ref, "inputs": inputs}
        await self._request(
            "POST",
            f"/repos/{self.settings.repository}/actions/workflows/{self.settings.workflow_file}/dispatches",
            json=payload,
            expected_status={204},
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        expected_status: set[int] | None = None,
        **kwargs: Any,
    ) -> Any:
        expected = expected_status or {200, 201}
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.settings.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with httpx.AsyncClient(base_url=self.settings.api_base_url, headers=headers, timeout=30) as client:
            response = await client.request(method, path, **kwargs)
        if response.status_code not in expected:
            detail = response.text[:500]
            raise GitHubAPIError(f"GitHub API returned {response.status_code} for {method} {path}: {detail}")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()


def candidate_count(candidate_data: dict[str, Any]) -> int:
    items = candidate_data.get("candidates")
    return len(items) if isinstance(items, list) else 0


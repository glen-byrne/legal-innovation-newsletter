"""Optional hosted dashboard for reviewing newsletter candidates."""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:  # Dashboard dependencies are optional.
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, RedirectResponse
    from fastapi.templating import Jinja2Templates
except ImportError as exc:  # pragma: no cover - exercised only when optional deps are missing.
    raise RuntimeError('Install dashboard dependencies with: python -m pip install ".[dashboard]"') from exc

from legal_innovator.dashboard.github import GitHubAPIError, GitHubClient, GitHubSettings, candidate_count
from legal_innovator.dashboard.selection import (
    build_editorial_selection_markdown,
    candidate_rows,
    selected_story_ids,
    story_source_links,
    validate_selection_count,
)


COOKIE_NAME = "ili_dashboard_session"
ISSUE_DATE_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app = FastAPI(title="The Irish Legal Innovator Review Dashboard")


@dataclass(frozen=True)
class DashboardSettings:
    github: GitHubSettings
    password: str | None
    secret_key: str
    allow_no_auth: bool = False
    cookie_secure: bool = True


def load_dashboard_settings() -> DashboardSettings:
    load_dotenv()
    repository = os.getenv("DASHBOARD_GITHUB_REPOSITORY") or os.getenv("GITHUB_REPOSITORY")
    token = os.getenv("DASHBOARD_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not repository:
        raise RuntimeError("Set DASHBOARD_GITHUB_REPOSITORY or GITHUB_REPOSITORY, for example glen-byrne/legal-innovation-newsletter.")
    if not token:
        raise RuntimeError("Set DASHBOARD_GITHUB_TOKEN or GITHUB_TOKEN with repository contents and workflow permissions.")
    password = os.getenv("DASHBOARD_PASSWORD")
    secret_key = os.getenv("DASHBOARD_SECRET_KEY") or token[-32:]
    return DashboardSettings(
        github=GitHubSettings(
            repository=repository,
            token=token,
            base_branch=os.getenv("DASHBOARD_BASE_BRANCH", os.getenv("GITHUB_BASE_BRANCH", "main")),
            workflow_file=os.getenv("DASHBOARD_WORKFLOW_FILE", "generate-newsletter.yml"),
        ),
        password=password,
        secret_key=secret_key,
        allow_no_auth=os.getenv("DASHBOARD_ALLOW_NO_AUTH", "false").lower() == "true",
        cookie_secure=os.getenv("DASHBOARD_COOKIE_SECURE", "true").lower() == "true",
    )


def session_cookie_value(settings: DashboardSettings) -> str:
    payload = settings.password or "no-auth"
    return hmac.new(settings.secret_key.encode("utf-8"), payload.encode("utf-8"), sha256).hexdigest()


def is_authenticated(request: Request, settings: DashboardSettings) -> bool:
    if settings.allow_no_auth:
        return True
    if not settings.password:
        return False
    cookie = request.cookies.get(COOKIE_NAME)
    return bool(cookie and hmac.compare_digest(cookie, session_cookie_value(settings)))


def login_redirect(request: Request, settings: DashboardSettings) -> RedirectResponse | None:
    if is_authenticated(request, settings):
        return None
    return RedirectResponse(url="/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login(request: Request, error: str | None = None):
    try:
        settings = load_dashboard_settings()
    except RuntimeError as exc:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"request": request, "setup_error": str(exc), "error": None},
        )
    if is_authenticated(request, settings):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "setup_error": None, "error": error},
    )


@app.post("/login")
async def login_submit(request: Request):
    settings = load_dashboard_settings()
    form = await request.form()
    password = str(form.get("password", ""))
    if not settings.password or not hmac.compare_digest(password, settings.password):
        return RedirectResponse(url="/login?error=Invalid%20password", status_code=303)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        session_cookie_value(settings),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return response


@app.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, message: str | None = None):
    settings = load_dashboard_settings()
    redirect = login_redirect(request, settings)
    if redirect:
        return redirect
    client = GitHubClient(settings.github)
    dates = await client.list_issue_dates()
    rows = []
    for issue_date in dates:
        branch = f"newsletter/{issue_date}"
        rows.append(
            {
                "date": issue_date,
                "branch": branch,
                "has_branch": await client.branch_exists(branch),
                "url": f"/issues/{issue_date}",
            }
        )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "message": message,
            "dates": rows,
            "repository": settings.github.repository,
            "base_branch": settings.github.base_branch,
        },
    )


@app.get("/issues/{issue_date}", response_class=HTMLResponse)
async def issue_detail(
    request: Request,
    issue_date: str,
    message: str | None = None,
    error: str | None = None,
):
    settings = load_dashboard_settings()
    redirect = login_redirect(request, settings)
    if redirect:
        return redirect
    _validate_issue_date(issue_date)
    return await _render_issue(request, settings, issue_date, message=message, error=error)


@app.post("/issues/{issue_date}/start")
async def start_draft(request: Request, issue_date: str):
    settings = load_dashboard_settings()
    redirect = login_redirect(request, settings)
    if redirect:
        return redirect
    _validate_issue_date(issue_date)
    client = GitHubClient(settings.github)
    await client.dispatch_workflow(settings.github.base_branch, _workflow_inputs(issue_date))
    return RedirectResponse(
        url=f"/issues/{issue_date}?message=Draft%20workflow%20started%20from%20main",
        status_code=303,
    )


@app.post("/issues/{issue_date}/save")
async def save_selection(request: Request, issue_date: str):
    settings = load_dashboard_settings()
    redirect = login_redirect(request, settings)
    if redirect:
        return redirect
    _validate_issue_date(issue_date)
    client = GitHubClient(settings.github)
    branch = f"newsletter/{issue_date}"
    if not await client.branch_exists(branch):
        return await _render_issue(request, settings, issue_date, error=f"Draft branch {branch} does not exist yet.")
    shortlist, _ = await client.get_json(f"issues/{issue_date}/review_shortlist.json", branch)
    form = await request.form()
    selected_ids = [str(value) for value in form.getlist("selected")]
    error = validate_selection_count(
        selected_ids,
        int(shortlist.get("min_final_stories", 8)),
        int(shortlist.get("max_final_stories", 12)),
    )
    if error:
        return await _render_issue(request, settings, issue_date, error=error, override_selected_ids=selected_ids)
    markdown = build_editorial_selection_markdown(shortlist, selected_ids)
    await client.put_text(
        f"issues/{issue_date}/editorial_selection.md",
        branch,
        markdown,
        f"Update editorial selection for {issue_date}",
    )
    action = str(form.get("action", "save"))
    if action == "save_and_generate":
        await client.dispatch_workflow(branch, _workflow_inputs(issue_date))
        message = "Selection saved and regeneration workflow started."
    else:
        message = "Selection saved."
    return RedirectResponse(url=f"/issues/{issue_date}?message={message.replace(' ', '%20')}", status_code=303)


async def _render_issue(
    request: Request,
    settings: DashboardSettings,
    issue_date: str,
    *,
    message: str | None = None,
    error: str | None = None,
    override_selected_ids: list[str] | None = None,
) -> HTMLResponse:
    client = GitHubClient(settings.github)
    branch = f"newsletter/{issue_date}"
    has_branch = await client.branch_exists(branch)
    candidate_data: dict[str, Any] | None = None
    candidate_error = None
    try:
        candidate_data, _ = await client.get_json(f"issues/{issue_date}/candidates.json", settings.github.base_branch)
    except (GitHubAPIError, ValueError) as exc:
        candidate_error = str(exc)

    shortlist: dict[str, Any] | None = None
    shortlist_error = None
    if has_branch:
        try:
            shortlist, _ = await client.get_json(f"issues/{issue_date}/review_shortlist.json", branch)
        except (GitHubAPIError, ValueError) as exc:
            shortlist_error = str(exc)

    selected_ids = override_selected_ids or (selected_story_ids(shortlist) if shortlist else [])
    return templates.TemplateResponse(
        request,
        "issue.html",
        {
            "request": request,
            "issue_date": issue_date,
            "branch": branch,
            "has_branch": has_branch,
            "candidate_count": candidate_count(candidate_data or {}),
            "candidate_rows": candidate_rows(candidate_data or {}),
            "candidate_error": candidate_error,
            "shortlist": shortlist,
            "shortlist_error": shortlist_error,
            "selected_ids": set(selected_ids),
            "selected_count": len(selected_ids),
            "story_source_links": story_source_links,
            "message": message,
            "error": error,
            "repository_url": settings.github.web_base_url,
            "pull_request_url": f"{settings.github.web_base_url}/pulls?q=head%3A{branch}",
        },
    )


def _workflow_inputs(issue_date: str) -> dict[str, str]:
    return {
        "run_date": issue_date,
        "maximum_final_stories": "12",
        "maximum_review_stories": "30",
        "maximum_candidates": "80",
        "candidate_file": "",
    }


def _validate_issue_date(issue_date: str) -> None:
    if not ISSUE_DATE_RE.match(issue_date):
        raise HTTPException(status_code=404, detail="Invalid issue date")

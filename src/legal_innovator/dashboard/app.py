"""Optional hosted dashboard for reviewing newsletter candidates."""

from __future__ import annotations

import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel

try:  # Dashboard dependencies are optional.
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, RedirectResponse
    from fastapi.templating import Jinja2Templates
except ImportError as exc:  # pragma: no cover - exercised only when optional deps are missing.
    raise RuntimeError('Install dashboard dependencies with: python -m pip install ".[dashboard]"') from exc

from legal_innovator.archive import write_issue_outputs
from legal_innovator.ai import StructuredAIClient
from legal_innovator.candidates import CandidateImportResult, load_candidate_file, rank_imported_clusters
from legal_innovator.config import RunWindow, Settings, bool_env, compute_run_window, load_settings
from legal_innovator.dashboard.github import GitHubClient, GitHubSettings, candidate_count
from legal_innovator.dashboard.selection import (
    build_editorial_selection_markdown,
    candidate_rows,
    story_region_tags,
    story_source_links,
    validate_selection_count,
)
from legal_innovator.models import Issue, RankedStory, ReviewShortlist
from legal_innovator.publishing import create_brevo_draft_from_issue_dir, load_brevo_settings_from_env
from legal_innovator.rendering.html import render_html
from legal_innovator.selection import (
    order_stories_by_selection,
    parse_selected_cluster_ids,
    render_selection_markdown,
    select_stories,
)


COOKIE_NAME = "lin_dashboard_session"
ISSUE_DATE_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")
ISSUES_DIR = Path("issues")
SCAN_PROMPT_PATH = Path("docs/codex-news-scan-prompt.md")


class DashboardIntro(BaseModel):
    intro: str

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app = FastAPI(title="Legal Innovation Newsletter Dashboard")


@dataclass(frozen=True)
class DashboardSettings:
    github: GitHubSettings | None
    password: str | None
    secret_key: str
    allow_no_auth: bool = False
    cookie_secure: bool = True


def load_dashboard_settings() -> DashboardSettings:
    load_dotenv()
    repository = os.getenv("DASHBOARD_GITHUB_REPOSITORY") or os.getenv("GITHUB_REPOSITORY")
    token = os.getenv("DASHBOARD_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    password = os.getenv("DASHBOARD_PASSWORD")
    secret_key = os.getenv("DASHBOARD_SECRET_KEY") or (token[-32:] if token else "local-dashboard-secret")
    github = None
    if repository and token:
        github = GitHubSettings(
            repository=repository,
            token=token,
            base_branch=os.getenv("DASHBOARD_BASE_BRANCH", os.getenv("GITHUB_BASE_BRANCH", "main")),
            workflow_file=os.getenv("DASHBOARD_WORKFLOW_FILE", "generate-newsletter.yml"),
        )
    return DashboardSettings(
        github=github,
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
    rows = _local_issue_rows()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "message": message,
            "dates": rows,
            "repository": settings.github.repository if settings.github else "local files",
            "base_branch": settings.github.base_branch if settings.github else "local workspace",
            "scan_prompt": _scan_prompt_text(),
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
    return _render_issue(request, settings, issue_date, message=message, error=error)


@app.post("/issues/{issue_date}/start")
async def start_draft(request: Request, issue_date: str):
    settings = load_dashboard_settings()
    redirect = login_redirect(request, settings)
    if redirect:
        return redirect
    if not settings.github:
        return RedirectResponse(
            url=f"/issues/{issue_date}?error=GitHub%20workflow%20controls%20need%20DASHBOARD_GITHUB_REPOSITORY%20and%20DASHBOARD_GITHUB_TOKEN",
            status_code=303,
        )
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
    if not settings.github:
        return await save_local_selection(request, issue_date)
    client = GitHubClient(settings.github)
    branch = f"newsletter/{issue_date}"
    if not await client.branch_exists(branch):
        return _render_issue(request, settings, issue_date, error=f"Draft branch {branch} does not exist yet.")
    shortlist, _ = await client.get_json(f"issues/{issue_date}/review_shortlist.json", branch)
    form = await request.form()
    selected_ids = [str(value) for value in form.getlist("selected")]
    error = validate_selection_count(
        selected_ids,
        int(shortlist.get("min_final_stories", 8)),
        int(shortlist.get("max_final_stories", 0)),
    )
    if error:
        return _render_issue(request, settings, issue_date, error=error, override_selected_ids=selected_ids)
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


@app.post("/issues/{issue_date}/generate-html")
async def generate_html(request: Request, issue_date: str):
    settings = load_dashboard_settings()
    redirect = login_redirect(request, settings)
    if redirect:
        return redirect
    _validate_issue_date(issue_date)
    form = await request.form()
    selected_ids = [str(value) for value in form.getlist("selected")]
    region_tag_overrides = _region_tag_overrides_from_form(form)
    context = _local_issue_context(issue_date, override_selected_ids=selected_ids)
    if context["error"]:
        return _render_issue(request, settings, issue_date, error=context["error"], override_selected_ids=selected_ids)
    shortlist = context["shortlist"]
    if not shortlist:
        return _render_issue(request, settings, issue_date, error="No candidate file was found.", override_selected_ids=selected_ids)
    error = validate_selection_count(
        selected_ids,
        int(shortlist.min_final_stories),
        int(shortlist.max_final_stories),
    )
    if error:
        return _render_issue(request, settings, issue_date, error=error, override_selected_ids=selected_ids)
    issue, review_shortlist = _build_local_issue(context, selected_ids, region_tag_overrides)
    issue_dir = _issue_dir(issue_date)
    selection_markdown = render_selection_markdown(review_shortlist)
    files = write_issue_outputs(
        issue,
        issue_dir,
        qa_report_markdown=_local_qa_markdown(issue, context["import_result"]),
        review_shortlist=review_shortlist,
        selection_markdown=selection_markdown,
    )
    return RedirectResponse(
        url=f"/issues/{issue_date}/html?message=Newsletter%20HTML%20generated%20at%20{files['html'].as_posix()}",
        status_code=303,
    )


@app.get("/issues/{issue_date}/generate-html")
async def generate_html_get(request: Request, issue_date: str):
    settings = load_dashboard_settings()
    redirect = login_redirect(request, settings)
    if redirect:
        return redirect
    _validate_issue_date(issue_date)
    return RedirectResponse(url=f"/issues/{issue_date}", status_code=303)


@app.get("/issues/{issue_date}/html", response_class=HTMLResponse)
async def generated_html(request: Request, issue_date: str, message: str | None = None, error: str | None = None):
    settings = load_dashboard_settings()
    redirect = login_redirect(request, settings)
    if redirect:
        return redirect
    _validate_issue_date(issue_date)
    html_path = _issue_dir(issue_date) / "issue.html"
    html_content = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    brevo_configured = False
    if html_content:
        try:
            brevo_configured = load_brevo_settings_from_env() is not None
        except ValueError as exc:
            error = error or str(exc)
    return templates.TemplateResponse(
        request,
        "html_output.html",
        {
            "request": request,
            "issue_date": issue_date,
            "html_content": html_content,
            "html_path": html_path,
            "message": message,
            "error": error if error else (None if html_content else "No generated HTML file exists yet."),
            "brevo_configured": brevo_configured,
            "brevo_app_url": "https://app.brevo.com/camp/listing",
        },
    )


@app.post("/issues/{issue_date}/brevo-draft")
async def create_brevo_draft(request: Request, issue_date: str):
    settings = load_dashboard_settings()
    redirect = login_redirect(request, settings)
    if redirect:
        return redirect
    _validate_issue_date(issue_date)
    try:
        campaign_id = create_brevo_draft_from_issue_dir(_issue_dir(issue_date))
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(
            url=f"/issues/{issue_date}/html?error={_url_escape(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/issues/{issue_date}/html?message={_url_escape(f'Brevo draft created. Campaign ID: {campaign_id}')}",
        status_code=303,
    )


async def save_local_selection(request: Request, issue_date: str):
    form = await request.form()
    selected_ids = [str(value) for value in form.getlist("selected")]
    region_tag_overrides = _region_tag_overrides_from_form(form)
    context = _local_issue_context(issue_date, override_selected_ids=selected_ids)
    if context["error"]:
        settings = load_dashboard_settings()
        return _render_issue(request, settings, issue_date, error=context["error"], override_selected_ids=selected_ids)
    shortlist = context["shortlist"]
    if not shortlist:
        settings = load_dashboard_settings()
        return _render_issue(request, settings, issue_date, error="No candidate file was found.", override_selected_ids=selected_ids)
    error = validate_selection_count(selected_ids, int(shortlist.min_final_stories), int(shortlist.max_final_stories))
    if error:
        settings = load_dashboard_settings()
        return _render_issue(request, settings, issue_date, error=error, override_selected_ids=selected_ids)
    _apply_region_tag_overrides(shortlist.stories, region_tag_overrides)
    updated_shortlist = shortlist.model_copy(update={"selected_cluster_ids": selected_ids})
    _issue_dir(issue_date).mkdir(parents=True, exist_ok=True)
    (_issue_dir(issue_date) / "editorial_selection.md").write_text(
        render_selection_markdown(updated_shortlist),
        encoding="utf-8",
    )
    action = str(form.get("action", "save"))
    if action == "save_and_generate":
        issue, review_shortlist = _build_local_issue(context, selected_ids, region_tag_overrides)
        write_issue_outputs(
            issue,
            _issue_dir(issue_date),
            qa_report_markdown=_local_qa_markdown(issue, context["import_result"]),
            review_shortlist=review_shortlist,
            selection_markdown=render_selection_markdown(review_shortlist),
        )
        return RedirectResponse(url=f"/issues/{issue_date}/html?message=Newsletter%20HTML%20generated", status_code=303)
    return RedirectResponse(url=f"/issues/{issue_date}?message=Selection%20saved", status_code=303)


def _render_issue(
    request: Request,
    settings: DashboardSettings,
    issue_date: str,
    *,
    message: str | None = None,
    error: str | None = None,
    override_selected_ids: list[str] | None = None,
) -> HTMLResponse:
    branch = f"newsletter/{issue_date}"
    context = _local_issue_context(issue_date, override_selected_ids=override_selected_ids)
    candidate_data = context["candidate_data"]
    shortlist = context["shortlist"]
    selected_ids = context["selected_ids"]
    html_exists = (_issue_dir(issue_date) / "issue.html").exists()
    return templates.TemplateResponse(
        request,
        "issue.html",
        {
            "request": request,
            "issue_date": issue_date,
            "branch": branch,
            "has_branch": settings.github is not None,
            "candidate_count": candidate_count(candidate_data or {}),
            "candidate_rows": candidate_rows(candidate_data or {}),
            "candidate_error": context["candidate_error"],
            "shortlist": shortlist,
            "shortlist_error": context["error"],
            "selected_ids": set(selected_ids),
            "selected_count": len(selected_ids),
            "story_region_tags": story_region_tags,
            "story_source_links": story_source_links,
            "message": message,
            "error": error,
            "repository_url": settings.github.web_base_url if settings.github else "",
            "pull_request_url": f"{settings.github.web_base_url}/pulls?q=head%3A{branch}" if settings.github else "",
            "html_exists": html_exists,
            "html_url": f"/issues/{issue_date}/html",
        },
    )


def _local_issue_rows() -> list[dict[str, Any]]:
    if not ISSUES_DIR.exists():
        return []
    rows = []
    for path in sorted((item for item in ISSUES_DIR.iterdir() if item.is_dir()), key=lambda item: item.name, reverse=True):
        if not ISSUE_DATE_RE.match(path.name):
            continue
        candidate_path = path / "candidates.json"
        issue_path = path / "issue.html"
        selection_path = path / "editorial_selection.md"
        rows.append(
            {
                "date": path.name,
                "url": f"/issues/{path.name}",
                "candidate_count": _candidate_count_from_path(candidate_path),
                "candidate_updated_at": _file_updated_at(candidate_path),
                "has_html": issue_path.exists(),
                "has_selection": selection_path.exists(),
                "html_url": f"/issues/{path.name}/html",
            }
        )
    return rows


def _local_issue_context(issue_date: str, override_selected_ids: list[str] | None = None) -> dict[str, Any]:
    issue_dir = _issue_dir(issue_date)
    candidate_path = issue_dir / "candidates.json"
    candidate_data: dict[str, Any] = {}
    candidate_error = None
    if not candidate_path.exists():
        return {
            "candidate_data": {},
            "candidate_error": f"{candidate_path} does not exist.",
            "shortlist": None,
            "selected_ids": override_selected_ids or [],
            "error": "No candidates.json file exists for this issue.",
            "import_result": None,
            "window": None,
            "settings": None,
        }
    try:
        candidate_data = json.loads(candidate_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        candidate_error = f"Invalid candidates.json: {exc}"

    settings = load_settings().model_copy(
        update={"dry_run_no_ai": True, "max_review_stories": 0, "max_final_stories": 0, "max_candidates": 0}
    )
    window = compute_run_window(settings, issue_date)
    try:
        imported = load_candidate_file(candidate_path, window)
    except Exception as exc:  # noqa: BLE001
        return {
            "candidate_data": candidate_data,
            "candidate_error": candidate_error,
            "shortlist": None,
            "selected_ids": override_selected_ids or [],
            "error": f"Candidate import failed: {exc}",
            "import_result": None,
            "window": window,
            "settings": settings,
        }
    review_stories = _limit_stories(rank_imported_clusters(imported.clusters, window, settings), settings.max_review_stories)
    _apply_candidate_editorial_text(review_stories, imported)
    selection_path = issue_dir / "editorial_selection.md"
    selected_ids = override_selected_ids
    if selected_ids is None:
        selected_ids = parse_selected_cluster_ids(selection_path)
    if not selected_ids:
        selected_ids = _limit_ids(imported.default_selected_cluster_ids, settings.max_final_stories)
    if not selected_ids:
        selected_ids = default_dashboard_selected_ids(review_stories, settings.max_final_stories)
    review_stories = order_stories_by_selection(review_stories, selected_ids)
    shortlist = ReviewShortlist(
        newsletter_name=settings.newsletter_name,
        run_date=window.issue_date,
        generated_at=datetime.now(window.run_at.tzinfo),
        window_start=window.start_at.date(),
        window_end=window.end_at.date(),
        min_final_stories=settings.min_final_stories,
        max_final_stories=settings.max_final_stories,
        selected_cluster_ids=selected_ids,
        stories=review_stories,
    )
    return {
        "candidate_data": candidate_data,
        "candidate_error": candidate_error,
        "shortlist": shortlist,
        "selected_ids": selected_ids,
        "error": None,
        "import_result": imported,
        "window": window,
        "settings": settings,
    }


def _region_tag_overrides_from_form(form: Any) -> dict[str, list[str]]:
    story_ids = [str(value) for value in form.getlist("region_tag_story") if str(value).strip()]
    overrides: dict[str, list[str]] = {story_id: [] for story_id in story_ids}
    for story_id in story_ids:
        key = f"region_tags__{story_id}"
        values = [str(value).strip() for value in form.getlist(key) if str(value).strip()]
        overrides[story_id] = values[:3]
    return overrides


def _apply_region_tag_overrides(stories: list[Any], overrides: dict[str, list[str]] | None) -> None:
    if not overrides:
        return
    for story in stories:
        story_id = str(getattr(story, "cluster_id", "") or (story.get("cluster_id", "") if isinstance(story, dict) else ""))
        if story_id not in overrides:
            continue
        if isinstance(story, dict):
            story["region_tags"] = overrides[story_id][:3]
        else:
            story.region_tags = overrides[story_id][:3]


def _build_local_issue(
    context: dict[str, Any],
    selected_ids: list[str],
    region_tag_overrides: dict[str, list[str]] | None = None,
) -> tuple[Issue, ReviewShortlist]:
    shortlist: ReviewShortlist = context["shortlist"]
    imported: CandidateImportResult = context["import_result"]
    window: RunWindow = context["window"]
    settings: Settings = context["settings"]
    _apply_region_tag_overrides(shortlist.stories, region_tag_overrides)
    selected_stories = select_stories(shortlist.stories, selected_ids)
    _apply_candidate_editorial_text(selected_stories, imported)
    issue = Issue(
        newsletter_name=settings.newsletter_name,
        run_date=window.issue_date,
        generated_at=datetime.now(window.run_at.tzinfo),
        window_start=window.start_at.date(),
        window_end=window.end_at.date(),
        intro=_issue_intro(selected_stories, load_settings()),
        stories=selected_stories,
        warnings=[],
    )
    review_shortlist = shortlist.model_copy(update={"selected_cluster_ids": [story.cluster_id for story in selected_stories]})
    return issue, review_shortlist


def _apply_candidate_editorial_text(stories: list[RankedStory], imported: CandidateImportResult) -> None:
    candidates = {candidate.id: candidate for candidate in imported.candidates}
    for story in stories:
        candidate = candidates.get(story.cluster_id)
        if not candidate:
            continue
        story.summary = candidate.factual_basis
        story.why_it_matters = candidate.legal_sector_relevance_note


def _issue_intro(stories: list[RankedStory], settings: Settings) -> str:
    if _dashboard_ai_intro_enabled(settings):
        generated = _ai_issue_intro(stories, settings)
        if generated:
            return generated
    return _local_intro(stories)


def _dashboard_ai_intro_enabled(settings: Settings) -> bool:
    if not bool_env(os.getenv("DASHBOARD_AI_INTRO", "true"), True):
        return False
    return bool(settings.openai_api_key and settings.openai_model_fast and settings.openai_model_high_quality)


def _ai_issue_intro(stories: list[RankedStory], settings: Settings) -> str | None:
    if not stories:
        return None
    ai_settings = settings.model_copy(update={"dry_run_no_ai": False})
    try:
        result = StructuredAIClient(ai_settings).complete_json(
            schema=DashboardIntro,
            system=(
                "You write concise executive newsletter introductions for The Legal Edge Ireland. "
                "Return JSON only. The intro must be a short overview of the main themes and trends across the selected stories. "
                "Do not list story headlines. Do not mention every item. Avoid hype and legal advice."
            ),
            user=_intro_prompt(stories),
            high_quality=False,
        )
    except Exception:  # noqa: BLE001 - dashboard generation should still work without AI.
        return None
    intro = " ".join(result.intro.split())
    if not intro:
        return None
    return intro


def _intro_prompt(stories: list[RankedStory]) -> str:
    lines = [
        "Draft a 1-2 sentence executive overview, around 45-75 words, for the top of this newsletter issue.",
        "Synthesize the issue's broad news themes and practical implications for Irish legal-sector readers.",
        "Do not write a list of the stories. Do not use bullet points.",
        "",
        "Selected stories:",
    ]
    for index, story in enumerate(stories, start=1):
        regions = ", ".join(story.region_tags) if story.region_tags else "Unspecified"
        lines.append(
            f"{index}. Headline: {story.headline}\n"
            f"Date: {story.date.isoformat()}\n"
            f"Regions: {regions}\n"
            f"Summary: {story.summary}\n"
            f"Why it matters: {story.why_it_matters}"
        )
    return "\n\n".join(lines)


def _local_intro(stories: list[RankedStory]) -> str:
    if not stories:
        return "No stories were selected for this issue."
    themes = _intro_themes(stories)
    region = _intro_region_focus(stories)
    if themes:
        return (
            f"This issue highlights {themes} across {region}, with selected developments pointing to practical changes "
            "in how legal work is delivered, governed, taught, and supported by technology."
        )
    return (
        f"This issue highlights legal innovation developments across {region}, with practical implications for legal "
        "services, courts, legal operations, professional practice, and client-facing risk."
    )


def _intro_themes(stories: list[RankedStory]) -> str:
    text = " ".join(
        " ".join(
            [
                " ".join(story.headline.lower().split()),
                " ".join(story.summary.lower().split()),
                " ".join(story.why_it_matters.lower().split()),
            ]
        )
        for story in stories
    )
    theme_map = [
        ("court digitisation and digital justice", ["court", "courts", "portal", "remote", "digital justice", "probate"]),
        ("legal AI adoption", ["legal ai", "ai", "agent", "claude", "openai", "wordsmith"]),
        ("lawyer training and legal education", ["training", "education", "mooc", "law society", "educators"]),
        ("legal operations and workflow redesign", ["operations", "workflow", "matter", "document", "knowledge", "automation"]),
        ("access to justice and public-service delivery", ["access to justice", "legal aid", "disability", "public"]),
        ("professional governance and risk management", ["governance", "regulation", "professional", "risk", "guidance"]),
        ("legal-tech investment and market activity", ["funding", "raises", "investment", "acquisition", "startup"]),
    ]
    found: list[str] = []
    for label, needles in theme_map:
        if label in found:
            continue
        if any(needle in text for needle in needles):
            found.append(label)
    if not found:
        return ""
    if len(found) == 1:
        return found[0]
    if len(found) == 2:
        return f"{found[0]} and {found[1]}"
    return f"{found[0]}, {found[1]}, and {found[2]}"


def _intro_region_focus(stories: list[RankedStory]) -> str:
    tags = [tag for story in stories for tag in story.region_tags]
    if not tags:
        return "Ireland and wider legal markets"
    if tags.count("Ireland") >= max(1, len(stories) // 3):
        return "Ireland, with wider UK, EU, and global context where relevant"
    if "United Kingdom" in tags or "European Union" in tags:
        return "the UK and EU, with Irish relevance where material"
    return "global legal markets, with relevance for Irish legal-sector readers"


def _local_qa_markdown(issue: Issue, imported: CandidateImportResult | None) -> str:
    lines = [
        f"# QA report: {issue.run_date.isoformat()}",
        "",
        "**Status:** Generated locally from Codex candidate research and dashboard editorial selection.",
        "",
        "## Checklist",
        f"- [{'x' if len(issue.stories) >= 8 else ' '}] issue contains at least 8 selected stories",
        "- [x] every rendered story has at least one source link",
        "- [x] visible scoring is not included",
        "- [x] disclaimer is included",
        "",
        "## Notes",
        "- This local dashboard generation does not send email and does not create beehiiv drafts.",
        "- Story summaries use the factual basis supplied in `candidates.json`.",
        "- Why-it-matters lines use the legal-sector relevance notes supplied in `candidates.json`.",
    ]
    if imported and imported.errors:
        lines.extend(["", "## Candidate import warnings"])
        lines.extend(f"- {error.message}" for error in imported.errors)
    return "\n".join(lines) + "\n"


def _candidate_count_from_path(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return candidate_count(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return 0


def _file_updated_at(path: Path) -> str:
    if not path.exists():
        return "No candidate file"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def _scan_prompt_text() -> str:
    if not SCAN_PROMPT_PATH.exists():
        return ""
    content = SCAN_PROMPT_PATH.read_text(encoding="utf-8").strip()
    start_marker = "```text"
    end_marker = "```"
    start = content.find(start_marker)
    if start == -1:
        return content
    start += len(start_marker)
    end = content.find(end_marker, start)
    if end == -1:
        return content[start:].strip()
    return content[start:end].strip()


def _limit_stories(stories: list[RankedStory], limit: int) -> list[RankedStory]:
    return stories if limit <= 0 else stories[:limit]


def _limit_ids(values: list[str], limit: int) -> list[str]:
    return values if limit <= 0 else values[:limit]


def default_dashboard_selected_ids(stories: list[RankedStory], limit: int) -> list[str]:
    if limit <= 0:
        return [story.cluster_id for story in stories]
    return [story.cluster_id for story in stories[:limit]]


def _issue_dir(issue_date: str) -> Path:
    return ISSUES_DIR / issue_date


def _workflow_inputs(issue_date: str) -> dict[str, str]:
    return {
        "run_date": issue_date,
        "maximum_final_stories": "0",
        "maximum_review_stories": "0",
        "maximum_candidates": "0",
        "candidate_file": "",
    }


def _validate_issue_date(issue_date: str) -> None:
    if not ISSUE_DATE_RE.match(issue_date):
        raise HTTPException(status_code=404, detail="Invalid issue date")


def _url_escape(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")

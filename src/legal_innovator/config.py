"""Configuration loading for The Irish Legal Innovator."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pydantic import BaseModel, Field


DEFAULT_TIMEZONE = "Europe/Dublin"


class Settings(BaseModel):
    openai_api_key: str | None = None
    openai_model_high_quality: str | None = None
    openai_model_fast: str | None = None
    max_candidates: int = Field(default=150, ge=1)
    max_shortlist: int = Field(default=40, ge=1)
    max_final_stories: int = Field(default=12, ge=1, le=12)
    min_final_stories: int = Field(default=8, ge=1, le=12)
    max_sources_per_story: int = Field(default=3, ge=1, le=3)
    max_extract_chars_per_article: int = Field(default=6000, ge=500)
    require_human_review: bool = True
    dry_run_no_ai: bool = False
    enable_openai_web_search: bool = False
    newsletter_name: str = "The Irish Legal Innovator"
    newsletter_sender_name: str | None = None
    newsletter_sender_email: str | None = None
    beehiiv_api_key: str | None = None
    beehiiv_publication_id: str | None = None
    timezone: str = DEFAULT_TIMEZONE
    github_token: str | None = None
    github_repository: str | None = None
    github_base_branch: str = "main"

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def validate_for_live_ai(self) -> None:
        if self.dry_run_no_ai:
            return
        missing = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.openai_model_high_quality:
            missing.append("OPENAI_MODEL_HIGH_QUALITY")
        if not self.openai_model_fast:
            missing.append("OPENAI_MODEL_FAST")
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Missing required environment variables for live AI generation: {joined}")


@dataclass(frozen=True)
class RunWindow:
    run_at: datetime
    start_at: datetime
    end_at: datetime

    @property
    def issue_date(self):
        return self.run_at.date()


def bool_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_settings(env_file: str | Path | None = ".env") -> Settings:
    if env_file:
        load_dotenv(env_file, override=False)
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model_high_quality=os.getenv("OPENAI_MODEL_HIGH_QUALITY"),
        openai_model_fast=os.getenv("OPENAI_MODEL_FAST"),
        max_candidates=int(os.getenv("MAX_CANDIDATES", "150")),
        max_shortlist=int(os.getenv("MAX_SHORTLIST", "40")),
        max_final_stories=int(os.getenv("MAX_FINAL_STORIES", "12")),
        min_final_stories=int(os.getenv("MIN_FINAL_STORIES", "8")),
        max_sources_per_story=int(os.getenv("MAX_SOURCES_PER_STORY", "3")),
        max_extract_chars_per_article=int(os.getenv("MAX_EXTRACT_CHARS_PER_ARTICLE", "6000")),
        require_human_review=bool_env(os.getenv("REQUIRE_HUMAN_REVIEW"), True),
        dry_run_no_ai=bool_env(os.getenv("DRY_RUN_NO_AI"), False),
        enable_openai_web_search=bool_env(os.getenv("ENABLE_OPENAI_WEB_SEARCH"), False),
        newsletter_name=os.getenv("NEWSLETTER_NAME", "The Irish Legal Innovator"),
        newsletter_sender_name=os.getenv("NEWSLETTER_SENDER_NAME"),
        newsletter_sender_email=os.getenv("NEWSLETTER_SENDER_EMAIL"),
        beehiiv_api_key=os.getenv("BEEHIIV_API_KEY"),
        beehiiv_publication_id=os.getenv("BEEHIIV_PUBLICATION_ID"),
        github_token=os.getenv("GITHUB_TOKEN"),
        github_repository=os.getenv("GITHUB_REPOSITORY"),
        github_base_branch=os.getenv("GITHUB_BASE_BRANCH", os.getenv("GITHUB_REF_NAME", "main")),
    )


def compute_run_window(settings: Settings, run_date: str | None = None) -> RunWindow:
    tzinfo = settings.tzinfo
    if run_date:
        if len(run_date) == 10:
            run_at = datetime.fromisoformat(f"{run_date}T23:59:59").replace(tzinfo=tzinfo)
        else:
            parsed = datetime.fromisoformat(run_date)
            run_at = parsed.replace(tzinfo=tzinfo) if parsed.tzinfo is None else parsed.astimezone(tzinfo)
    else:
        run_at = datetime.now(tzinfo)
    start_at = run_at - timedelta(days=14)
    return RunWindow(run_at=run_at, start_at=start_at, end_at=run_at)

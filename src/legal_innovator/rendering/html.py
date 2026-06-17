"""Email-safe HTML rendering."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from legal_innovator.models import Issue


SUBSCRIBE_URL = (
    "https://c7c6d749.sibforms.com/serve/"
    "MUIFALRrvBQiZW3BrorjTMVnSZm_FjibWRHJAC9aajlSAlxD6Ta5O5D4LLFYYxgU8SOD7zkG9_XS_nFND-"
    "rLcSgScnD1Obnq7of7_GMXsEjt44REw_FE0WXiLFc8oBX0_Mza10rcFnb6QQ-TOf7xzpcfeoVt18y_gi-"
    "Atdyz5fWq9c9wamwovHB9jtPihPFwsA57Jm__wBEA-bo1fw=="
)
UNSUBSCRIBE_URL = (
    "https://c7c6d749.sibforms.com/serve/"
    "MUIFABoS6DtrpdiUAgcUAmRT5l0cUTDOVCCLEDaKRorQ7Vu2X1Gz7n9CeQOYNhh-i5glgVSnO4svGou-"
    "hEn43dvUcqM5IabDx7ehox-sUYlSTrU_Tvz6OfgR85OkVf80q_oN_QciLWUPBdQsBEeQLa6hj5sPUIIJB6kyIDTjsUJGPehPLQilgAt5i9G5o-"
    "qgQXbkKD1AnZILELMM9A=="
)
DEFAULT_LOGO_URL = (
    "https://raw.githubusercontent.com/glen-byrne/legal-innovation-newsletter/main/"
    "src/legal_innovator/rendering/assets/the-legal-edge-logo-email.png"
)


def format_display_date(value: date) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def brand_icon_src() -> str:
    return os.getenv("NEWSLETTER_LOGO_URL", "").strip() or DEFAULT_LOGO_URL


def format_intro_body(value: str) -> str:
    intro = " ".join(value.split())
    lower = intro.lower()
    prefixes = [
        "in today's issue:",
        "in todays issue:",
        "this issue highlights",
        "this issue leads with",
        "this issue tracks",
        "this fortnight saw",
        "this fortnight,",
    ]
    for prefix in prefixes:
        if lower.startswith(prefix):
            intro = intro[len(prefix) :].lstrip(" :,-")
            break
    if intro:
        return intro[0].lower() + intro[1:]
    return "legal innovation developments across Ireland and comparable markets, with selected stories on technology, courts, operations, regulation and legal-service delivery."


def render_html(issue: Issue) -> str:
    template_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("email.html.j2")
    return template.render(
        issue=issue,
        format_date=format_display_date,
        brand_icon_src=brand_icon_src(),
        intro_body=format_intro_body(issue.intro),
        subscribe_url=SUBSCRIBE_URL,
        unsubscribe_url=UNSUBSCRIBE_URL,
    )

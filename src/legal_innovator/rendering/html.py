"""Email-safe HTML rendering."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from legal_innovator.models import Issue


def format_display_date(value: date) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def render_html(issue: Issue) -> str:
    template_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("email.html.j2")
    return template.render(issue=issue, format_date=format_display_date)

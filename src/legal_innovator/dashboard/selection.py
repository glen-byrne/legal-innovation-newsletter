"""Selection helpers for the optional hosted dashboard."""

from __future__ import annotations

from html import escape
from typing import Any

from legal_innovator.models import region_tags_for_region


def selected_story_ids(shortlist: dict[str, Any]) -> list[str]:
    values = shortlist.get("selected_cluster_ids", [])
    return [str(value) for value in values] if isinstance(values, list) else []


def validate_selection_count(selected_ids: list[str], minimum: int, maximum: int) -> str | None:
    count = len(selected_ids)
    if count < minimum:
        return f"Select at least {minimum} stories. You selected {count}."
    if maximum > 0 and count > maximum:
        return f"Select no more than {maximum} stories. You selected {count}."
    return None


def build_editorial_selection_markdown(shortlist: dict[str, Any], selected_ids: list[str]) -> str:
    selected = set(selected_ids)
    issue_date = shortlist["run_date"]
    newsletter_name = shortlist.get("newsletter_name", "The Legal Edge Ireland")
    minimum = shortlist.get("min_final_stories", 8)
    maximum = shortlist.get("max_final_stories", 0)
    lines = [
        f"# Editorial selection: {newsletter_name} - {issue_date}",
        "",
        _selection_instruction(int(minimum), int(maximum)),
        "Tick or untick the boxes, then rerun the generator for the same issue date to rebuild the final issue files.",
        "",
        "Do not edit the hidden `story:` identifiers inside the comments.",
        "",
    ]
    for index, story in enumerate(_ordered_stories(shortlist.get("stories", []), selected_ids), start=1):
        story_id = str(story.get("cluster_id", ""))
        checked = "x" if story_id in selected else " "
        headline = story.get("headline", "Untitled story")
        date = story.get("date", "")
        regions = ", ".join(story_region_tags(story))
        sources = "; ".join(
            f"{source.get('name', 'Source')}: {source.get('url', '')}" for source in story.get("sources", [])
        )
        lines.extend(
            [
                f"- [{checked}] <!-- story:{story_id} --> **{index}. {headline}** ({date})",
                f"  Regions: {regions}" if regions else "  Regions: Unspecified",
                f"  Sources: {sources}",
                "",
            ]
        )
    return "\n".join(lines)


def candidate_rows(candidate_data: dict[str, Any]) -> list[dict[str, Any]]:
    items = candidate_data.get("candidates", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def story_sources(story: dict[str, Any]) -> str:
    sources = _story_value(story, "sources", [])
    if not isinstance(sources, list):
        return ""
    return "; ".join(_story_value(source, "name", "Source") for source in sources)


def story_source_links(story: Any) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    sources = _story_value(story, "sources", [])
    if not isinstance(sources, list):
        return links
    for source in sources:
        links.append(
            {
                "name": str(_story_value(source, "name", "Source")),
                "url": str(_story_value(source, "url", "")),
            }
        )
    return links


def story_region_tags(story: Any) -> list[str]:
    tags = _story_value(story, "region_tags", [])
    if isinstance(tags, list) and tags:
        return [str(tag) for tag in tags if str(tag).strip()]
    region = _story_value(story, "region", "")
    if not region:
        return []
    return region_tags_for_region(str(region))


def safe_message(value: str | None) -> str:
    return escape(value or "", quote=True)


def _ordered_stories(stories: Any, selected_ids: list[str]) -> list[Any]:
    if not isinstance(stories, list):
        return []
    stories_by_id = {str(_story_value(story, "cluster_id", "")): story for story in stories}
    seen: set[str] = set()
    ordered: list[Any] = []
    for story_id in selected_ids:
        if story_id in seen:
            continue
        story = stories_by_id.get(story_id)
        if story:
            ordered.append(story)
            seen.add(story_id)
    ordered.extend(story for story in stories if str(_story_value(story, "cluster_id", "")) not in seen)
    return ordered


def _story_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _selection_instruction(minimum: int, maximum: int) -> str:
    if maximum <= 0:
        return f"Select at least {minimum} stories for the final newsletter."
    return f"Select {minimum}-{maximum} stories for the final newsletter."

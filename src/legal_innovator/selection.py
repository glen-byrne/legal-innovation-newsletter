"""Editorial shortlist and checkbox selection helpers."""

from __future__ import annotations

import re
from pathlib import Path

from legal_innovator.models import RankedStory, ReviewShortlist


CHECKBOX_RE = re.compile(r"^-\s+\[(?P<checked>[ xX])\]\s+<!--\s*story:(?P<id>[^ ]+)\s*-->")


def default_selected_cluster_ids(stories: list[RankedStory], max_final_stories: int) -> list[str]:
    if max_final_stories <= 0:
        return [story.cluster_id for story in stories]
    return [story.cluster_id for story in stories[:max_final_stories]]


def parse_selected_cluster_ids(path: str | Path) -> list[str]:
    selection_path = Path(path)
    if not selection_path.exists():
        return []
    selected: list[str] = []
    for line in selection_path.read_text(encoding="utf-8").splitlines():
        match = CHECKBOX_RE.match(line.strip())
        if match and match.group("checked").lower() == "x":
            selected.append(match.group("id"))
    return selected


def select_stories(stories: list[RankedStory], selected_cluster_ids: list[str]) -> list[RankedStory]:
    selected = set(selected_cluster_ids)
    return [story for story in order_stories_by_selection(stories, selected_cluster_ids) if story.cluster_id in selected]


def order_stories_by_selection(stories: list[RankedStory], selected_cluster_ids: list[str]) -> list[RankedStory]:
    stories_by_id = {story.cluster_id: story for story in stories}
    seen: set[str] = set()
    ordered: list[RankedStory] = []
    for story_id in selected_cluster_ids:
        if story_id in seen:
            continue
        story = stories_by_id.get(story_id)
        if story:
            ordered.append(story)
            seen.add(story_id)
    ordered.extend(story for story in stories if story.cluster_id not in seen)
    return ordered


def render_selection_markdown(shortlist: ReviewShortlist) -> str:
    selected = set(shortlist.selected_cluster_ids)
    lines = [
        f"# Editorial selection: {shortlist.newsletter_name} - {shortlist.run_date.isoformat()}",
        "",
        _selection_instruction(shortlist),
        "Tick or untick the boxes, then rerun the generator for the same issue date to rebuild the final issue files.",
        "",
        "Do not edit the hidden `story:` identifiers inside the comments.",
        "",
    ]
    for index, story in enumerate(order_stories_by_selection(shortlist.stories, shortlist.selected_cluster_ids), start=1):
        checked = "x" if story.cluster_id in selected else " "
        sources = "; ".join(f"{source.name}: {source.url}" for source in story.sources)
        regions = _region_tags_text(story)
        lines.extend(
            [
                f"- [{checked}] <!-- story:{story.cluster_id} --> **{index}. {story.headline}** ({story.date.isoformat()})",
                f"  Regions: {regions}" if regions else "  Regions: Unspecified",
                f"  Sources: {sources}",
                "",
            ]
        )
    return "\n".join(lines)


def _selection_instruction(shortlist: ReviewShortlist) -> str:
    if shortlist.max_final_stories <= 0:
        return f"Select at least {shortlist.min_final_stories} stories for the final newsletter."
    return f"Select {shortlist.min_final_stories}-{shortlist.max_final_stories} stories for the final newsletter."


def _region_tags_text(story: RankedStory) -> str:
    return ", ".join(story.region_tags)

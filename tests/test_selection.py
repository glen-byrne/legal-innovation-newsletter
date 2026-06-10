from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from legal_innovator.models import RankedStory, ReviewShortlist, SourceLink
from legal_innovator.selection import (
    default_selected_cluster_ids,
    parse_selected_cluster_ids,
    render_selection_markdown,
    select_stories,
)


def make_ranked_stories(count: int = 30) -> list[RankedStory]:
    run_at = datetime(2026, 5, 20, 12, 0, tzinfo=ZoneInfo("Europe/Dublin"))
    return [
        RankedStory(
            headline=f"Review story {index + 1}",
            date=(run_at - timedelta(days=index % 14)).date(),
            canonical_url=f"https://example.com/review-{index}",
            sources=[SourceLink(name="Example", url=f"https://example.com/review-{index}")],
            cluster_id=f"cluster-{index}",
        )
        for index in range(count)
    ]


def test_default_selection_checks_top_final_stories() -> None:
    stories = make_ranked_stories(30)

    selected = default_selected_cluster_ids(stories, 12)

    assert selected == [f"cluster-{index}" for index in range(12)]


def test_default_selection_can_be_uncapped() -> None:
    stories = make_ranked_stories(30)

    selected = default_selected_cluster_ids(stories, 0)

    assert selected == [f"cluster-{index}" for index in range(30)]


def test_render_and_parse_editorial_selection(tmp_path: Path) -> None:
    stories = make_ranked_stories(3)
    shortlist = ReviewShortlist(
        newsletter_name="The Legal Innovator Ireland",
        run_date=stories[0].date,
        generated_at=datetime(2026, 5, 20, 12, 0, tzinfo=ZoneInfo("Europe/Dublin")),
        window_start=stories[0].date - timedelta(days=14),
        window_end=stories[0].date,
        min_final_stories=8,
        max_final_stories=12,
        selected_cluster_ids=["cluster-0", "cluster-2"],
        stories=stories,
    )
    markdown = render_selection_markdown(shortlist)
    path = tmp_path / "editorial_selection.md"
    path.write_text(markdown, encoding="utf-8")

    assert parse_selected_cluster_ids(path) == ["cluster-0", "cluster-2"]
    assert select_stories(stories, ["cluster-2"])[0].headline == "Review story 3"

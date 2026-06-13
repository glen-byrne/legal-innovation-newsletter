from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from legal_innovator.candidates import load_candidate_file, rank_imported_clusters
from legal_innovator.config import RunWindow, Settings


def test_candidate_file_import_keeps_all_candidate_rows_for_editorial_selection(tmp_path: Path) -> None:
    candidate_file = tmp_path / "candidates.json"
    candidate_file.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "id": "ILIN-2026-05-24-001",
                        "headline": "Legal AI platform announces major court workflow partnership",
                        "published_date": "2026-05-20",
                        "source_name": "Example Legal News",
                        "source_url": "https://example.com/legal-ai-platform",
                        "event_type": "funding_acquisition_partnership",
                        "source_origin": "confirmed_reporting",
                        "region": "UK/EU",
                        "factual_basis": "A reported partnership affects litigation workflow tools.",
                        "legal_sector_relevance_note": "The development may affect court-facing legal AI workflows.",
                        "duplicate_group": "DG-001",
                        "warning_flags": "none",
                        "selected": True,
                    },
                    {
                        "id": "ILIN-2026-05-24-002",
                        "headline": "Second report on legal AI court workflow partnership",
                        "published_date": "2026-05-20",
                        "source_name": "Example Business News",
                        "source_url": "https://example.com/legal-ai-platform-second",
                        "event_type": "funding_acquisition_partnership",
                        "source_origin": "secondary_reporting",
                        "region": "UK/EU",
                        "factual_basis": "A second source reports the same underlying partnership.",
                        "legal_sector_relevance_note": "The second report corroborates the legal-sector significance.",
                        "duplicate_group": "DG-001",
                        "warning_flags": ["possible_duplicate"],
                        "selected": True,
                    },
                    {
                        "id": "ILIN-2026-05-24-003",
                        "headline": "Near miss broad technology policy story",
                        "published_date": "2026-05-21",
                        "source_name": "Example Tech News",
                        "source_url": "https://example.com/broad-tech",
                        "event_type": "other",
                        "source_origin": "confirmed_reporting",
                        "region": "global",
                        "factual_basis": "A broad technology policy story.",
                        "legal_sector_relevance_note": "Limited direct legal-sector significance.",
                        "duplicate_group": "none",
                        "warning_flags": "limited_detail",
                        "selected": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    run_at = datetime(2026, 5, 24, 23, 59, tzinfo=ZoneInfo("Europe/Dublin"))
    window = RunWindow(run_at=run_at, start_at=run_at - timedelta(days=14), end_at=run_at)

    result = load_candidate_file(candidate_file, window)

    assert not result.errors
    assert len(result.candidates) == 3
    assert len(result.clusters) == 3
    assert [cluster.cluster_id for cluster in result.clusters] == [
        "ILIN-2026-05-24-001",
        "ILIN-2026-05-24-002",
        "ILIN-2026-05-24-003",
    ]
    assert result.default_selected_cluster_ids == ["ILIN-2026-05-24-001", "ILIN-2026-05-24-002"]

    ranked = rank_imported_clusters(result.clusters, window, Settings(dry_run_no_ai=True))

    assert ranked[0].headline == "Legal AI platform announces major court workflow partnership"
    assert ranked[0].region_tags == ["United Kingdom", "European Union"]
    assert ranked[1].headline == "Second report on legal AI court workflow partnership"
    assert ranked[2].headline == "Near miss broad technology policy story"
    assert ranked[2].region_tags == ["Global"]


def test_candidate_file_import_flags_out_of_window_items(tmp_path: Path) -> None:
    candidate_file = tmp_path / "candidates.json"
    candidate_file.write_text(
        json.dumps(
            [
                {
                    "id": "ILIN-2026-05-24-001",
                    "headline": "Old legal innovation story",
                    "published_date": "2026-05-01",
                    "source_name": "Example Legal News",
                    "source_url": "https://example.com/old-story",
                    "event_type": "legal_ai_adoption",
                    "source_origin": "confirmed_reporting",
                    "region": "Ireland",
                    "factual_basis": "An old story outside the active issue window.",
                    "legal_sector_relevance_note": "Relevant but outside the date window.",
                    "duplicate_group": "none",
                    "warning_flags": "none",
                    "selected": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    run_at = datetime(2026, 5, 24, 23, 59, tzinfo=ZoneInfo("Europe/Dublin"))
    window = RunWindow(run_at=run_at, start_at=run_at - timedelta(days=14), end_at=run_at)

    result = load_candidate_file(candidate_file, window)

    assert result.clusters == []
    assert len(result.errors) == 1
    assert "outside 14-day window" in result.errors[0].message

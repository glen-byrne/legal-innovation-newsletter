"""CLI entrypoint for The Irish Legal Innovator pipeline."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from legal_innovator.archive import ArchiveStore, rendered_outputs, write_issue_outputs
from legal_innovator.classification import classify_articles
from legal_innovator.config import compute_run_window, load_settings
from legal_innovator.deduplication import cluster_articles
from legal_innovator.discovery import DiscoveryService, load_source_config
from legal_innovator.errors import ErrorStage, StageError
from legal_innovator.extraction import ExtractionService
from legal_innovator.models import Issue
from legal_innovator.pr import build_pr_body, create_pull_request
from legal_innovator.qa import render_qa_report, run_qa
from legal_innovator.ranking import rank_clusters
from legal_innovator.summarisation import summarise_issue


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "generate":
        return generate(args)
    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="legal-innovator")
    subparsers = parser.add_subparsers(dest="command")
    generate_parser = subparsers.add_parser("generate", help="Generate a newsletter issue")
    generate_parser.add_argument("--run-date", help="Run date in YYYY-MM-DD format")
    generate_parser.add_argument("--output-dir", help="Output directory, defaults to issues/YYYY-MM-DD")
    generate_parser.add_argument("--max-candidates", type=int, help="Override MAX_CANDIDATES")
    generate_parser.add_argument("--max-final-stories", type=int, help="Override MAX_FINAL_STORIES")
    generate_parser.add_argument("--no-pr", action="store_true", help="Generate locally without opening a pull request")
    generate_parser.add_argument("--pr-body-output", help="Optional path for the generated PR body")
    return parser


def generate(args: argparse.Namespace) -> int:
    stage_errors: list[StageError] = []
    settings = load_settings()
    update = {}
    if args.max_candidates:
        update["max_candidates"] = args.max_candidates
    if args.max_final_stories:
        update["max_final_stories"] = args.max_final_stories
    if update:
        settings = settings.model_copy(update=update)
    settings.validate_for_live_ai()
    window = compute_run_window(settings, args.run_date)
    output_dir = Path(args.output_dir or f"issues/{window.issue_date.isoformat()}")

    source_config = load_source_config()
    archive = ArchiveStore()

    try:
        discovery = DiscoveryService(settings)
        candidates = discovery.collect(source_config, window)
        stage_errors.extend(discovery.errors)
        source_diagnostics = discovery.diagnostics
        candidates = archive.filter_unseen_candidates(candidates)
    except Exception as exc:  # noqa: BLE001
        stage_errors.append(StageError(ErrorStage.SOURCE_ACCESS, str(exc)))
        source_diagnostics = []
        candidates = []

    try:
        extractor = ExtractionService(settings)
        extracted = extractor.extract_many(candidates)
        stage_errors.extend(extractor.errors)
        extracted = [
            article
            for article in extracted
            if article.published_at
            and window.start_at <= article.published_at.astimezone(window.run_at.tzinfo) <= window.end_at
        ]
    except Exception as exc:  # noqa: BLE001
        stage_errors.append(StageError(ErrorStage.EXTRACTION, str(exc)))
        extracted = []

    classified, classification_errors = classify_articles(extracted, settings)
    stage_errors.extend(classification_errors)

    clusters, dedupe_errors = cluster_articles(classified, settings)
    stage_errors.extend(dedupe_errors)
    clusters = archive.filter_unseen_clusters(clusters)

    ranked = rank_clusters(clusters, window, settings)[: settings.max_final_stories]
    ranked_cluster_ids = {story.cluster_id for story in ranked}
    selected_clusters = [cluster for cluster in clusters if cluster.cluster_id in ranked_cluster_ids]

    intro, stories, summary_errors = summarise_issue(ranked, selected_clusters, settings)
    stage_errors.extend(summary_errors)

    issue = Issue(
        newsletter_name=settings.newsletter_name,
        run_date=window.issue_date,
        generated_at=datetime.now(window.run_at.tzinfo),
        window_start=window.start_at.date(),
        window_end=window.end_at.date(),
        intro=intro,
        stories=stories,
        warnings=[],
    )
    rendered = rendered_outputs(issue)
    qa_report = run_qa(
        issue,
        window,
        settings,
        rendered,
        selected_clusters,
        stage_errors,
        source_diagnostics=source_diagnostics,
    )
    qa_markdown = render_qa_report(qa_report)
    pr_body = build_pr_body(issue, qa_report)
    files = write_issue_outputs(issue, output_dir, qa_report_markdown=qa_markdown)
    archive.record_issue(issue, selected_clusters)
    pr_body_path = Path(args.pr_body_output or ".newsletter_pr_body.md")
    pr_body_path.write_text(pr_body, encoding="utf-8")

    if not args.no_pr:
        try:
            create_pull_request(issue, pr_body_path)
        except Exception as exc:  # noqa: BLE001
            print(f"PR creation failed: {exc}", file=sys.stderr)
            return 2

    print(f"Generated {len(issue.stories)} stories in {output_dir}")
    print(f"QA status: {'passed' if qa_report.passed else 'needs attention'}")
    if not qa_report.passed:
        print("QA findings were recorded in qa_report.md and the PR body for human review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

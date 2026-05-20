"""Repo-file archive and repeat-prevention storage."""

from __future__ import annotations

import json
from pathlib import Path

from legal_innovator.models import CandidateArticle, Issue, RankedStory, ReviewShortlist, StoryCluster
from legal_innovator.rendering import render_html, render_markdown, render_plaintext


class ArchiveStore:
    def __init__(
        self,
        *,
        seen_urls_path: str | Path = "data/seen_urls.json",
        seen_clusters_path: str | Path = "data/seen_story_clusters.json",
    ) -> None:
        self.seen_urls_path = Path(seen_urls_path)
        self.seen_clusters_path = Path(seen_clusters_path)

    def load_seen_urls(self) -> set[str]:
        return set(_load_json_list(self.seen_urls_path))

    def load_seen_clusters(self) -> set[str]:
        return set(_load_json_list(self.seen_clusters_path))

    def filter_unseen_candidates(self, candidates: list[CandidateArticle]) -> list[CandidateArticle]:
        seen = self.load_seen_urls()
        return [candidate for candidate in candidates if candidate.canonical_url not in seen]

    def filter_unseen_clusters(self, clusters: list[StoryCluster]) -> list[StoryCluster]:
        seen = self.load_seen_clusters()
        return [cluster for cluster in clusters if cluster.fingerprint not in seen and cluster.cluster_id not in seen]

    def record_issue(self, issue: Issue, clusters: list[StoryCluster]) -> None:
        urls = self.load_seen_urls()
        fingerprints = self.load_seen_clusters()
        for story in issue.stories:
            urls.add(str(story.canonical_url).rstrip("/"))
            for source in story.sources:
                urls.add(str(source.url).rstrip("/"))
            if story.cluster_id:
                fingerprints.add(story.cluster_id)
        for cluster in clusters:
            if any(story.cluster_id == cluster.cluster_id for story in issue.stories):
                fingerprints.add(cluster.fingerprint)
        _write_json_list(self.seen_urls_path, sorted(urls))
        _write_json_list(self.seen_clusters_path, sorted(fingerprints))


def write_issue_outputs(
    issue: Issue,
    output_dir: str | Path,
    *,
    qa_report_markdown: str,
    review_shortlist: ReviewShortlist | None = None,
    selection_markdown: str | None = None,
    pr_body: str | None = None,
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    html = render_html(issue)
    markdown = render_markdown(issue)
    plaintext = render_plaintext(issue)
    files = {
        "json": output_path / "issue.json",
        "markdown": output_path / "issue.md",
        "html": output_path / "issue.html",
        "plaintext": output_path / "issue.txt",
        "qa": output_path / "qa_report.md",
    }
    files["json"].write_text(json.dumps(issue.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    files["markdown"].write_text(markdown, encoding="utf-8")
    files["html"].write_text(html, encoding="utf-8")
    files["plaintext"].write_text(plaintext, encoding="utf-8")
    files["qa"].write_text(qa_report_markdown, encoding="utf-8")
    if review_shortlist is not None:
        files["shortlist_json"] = output_path / "review_shortlist.json"
        files["shortlist_json"].write_text(
            json.dumps(review_shortlist.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
    if selection_markdown is not None:
        files["selection"] = output_path / "editorial_selection.md"
        files["selection"].write_text(selection_markdown, encoding="utf-8")
    if pr_body is not None:
        files["pr_body"] = output_path / "pr_body.md"
        files["pr_body"].write_text(pr_body, encoding="utf-8")
    return files


def rendered_outputs(issue: Issue) -> dict[str, str]:
    return {
        "html": render_html(issue),
        "markdown": render_markdown(issue),
        "plaintext": render_plaintext(issue),
    }


def _load_json_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def _write_json_list(path: Path, values: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")

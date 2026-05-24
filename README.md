# The Irish Legal Innovator

Lean MVP newsletter generation system for **The Irish Legal Innovator**, an executive-style legal innovation briefing.

The system discovers legal innovation news from the 14 days immediately before the run date, prioritises Irish relevance while allowing major UK/EU and global stories to outrank minor local items, and generates review-ready issue files for a human-approved GitHub pull request.

The MVP does **not** send email and does **not** create beehiiv drafts.

## Editorial Scope

The newsletter is for internal law firm leadership, lawyers, clients, in-house counsel, and legal-tech founders.

Tone: neutral, concise, professional, commercially aware. It avoids hype and legal advice.

In scope:

- AI in law
- Legal operations
- Court digitisation
- Regtech and compliance
- E-discovery
- Access to justice
- Legal education and legal design
- Smart contracts and blockchain
- Privacy and cyber governance
- Alternative legal services
- Legal-sector-relevant digital identity, cyber, AI regulation, or enterprise technology developments

The MVP prefers factual news over opinion, commentary, thought leadership, generic vendor marketing, and advertorial content. Vendor announcements are excluded unless a reputable third-party source supports a noteworthy development.

## Source Strategy

Default sources live in [data/sources.yaml](data/sources.yaml). The MVP starts with:

- Irish Tech News Legaltech
- Artificial Lawyer
- LawNext
- Legal IT Insider / LegalTechnology
- Law.com Legaltech News
- The Lawyer tech tag

The normal workflow is RSS/source-first. It does not use Google Alerts, and it does not scrape Google, Bing, or other search-engine result pages.

Discovery order:

1. RSS/feed discovery where configured.
2. Public source page, sitemap, and metadata discovery for sources without suitable RSS feeds.
3. Optional OpenAI API web search only when `ENABLE_OPENAI_WEB_SEARCH=true`.
4. Optional third-party news/search API adapters in future.

The default and recommended cost-control setting is `ENABLE_OPENAI_WEB_SEARCH=false`. In that mode, configured search queries are not run and do not appear as source diagnostics. They are retained only as an optional expanded-discovery fallback.

If no search API is configured, the system still runs from source lists, public source pages, RSS feeds, sitemaps, and permitted metadata.

## Codex-Assisted Fortnightly Workflow

The recommended low-cost workflow uses Codex for research discovery and the Python system for validation, selection, rendering, QA, archiving, and PR review:

1. Prompt Codex to gather 25-30 candidate stories using the agreed fortnightly legal-innovation news scan prompt.
2. Save the Codex output as JSON at `issues/YYYY-MM-DD/candidates.json`.
3. Commit and push the candidate file so GitHub Actions can read it.
4. Run the GitHub Actions workflow for the same issue date.
5. The workflow imports the candidate file, preserves Codex ranking, includes every in-window candidate row in `editorial_selection.md`, and uses `selected` only to decide which items start ticked by default.
6. Review `editorial_selection.md` and tick 8-12 final stories.
7. Rerun the workflow for the same issue date, using the same candidate file and edited selection file.
8. Review the generated PR and merge only when the issue is editorially approved.

This workflow is designed to minimise API spend while preserving source traceability and human editorial control. The legacy RSS/source discovery path remains available as a fallback when no candidate file is supplied.

## Candidate File Format

For the automated pipeline, ask Codex to return JSON rather than only a visual table. The candidate file may be either a JSON array or an object with a `candidates` array.

Example:

```json
{
  "candidates": [
    {
      "id": "ILIN-2026-05-24-001",
      "headline": "Example legal AI workflow story",
      "published_date": "2026-05-24",
      "source_name": "Example Legal News",
      "source_url": "https://example.com/story",
      "event_type": "legal_ai_adoption",
      "source_origin": "confirmed_reporting",
      "region": "UK/EU",
      "factual_basis": "The source reports a concrete legal workflow development.",
      "legal_sector_relevance_note": "The story may affect how legal teams adopt AI tools.",
      "duplicate_group": "none",
      "warning_flags": "none",
      "selected": true
    }
  ]
}
```

Supported `source_origin` values are `official_source`, `confirmed_reporting`, `reported_not_officially_confirmed`, `secondary_reporting`, and `vendor_originated_announcement`.

Use the prompt's required fields exactly: `id`, `headline`, `published_date`, `source_name`, `source_url`, `event_type`, `source_origin`, `region`, `factual_basis`, `legal_sector_relevance_note`, `duplicate_group`, `warning_flags`, and `selected`.

The importer:

- Requires direct `http` or `https` source URLs.
- Excludes candidates outside the 14-day window.
- Includes `selected=false` items in the shortlist, unticked by default.
- Keeps candidates with the same `duplicate_group` visible as separate rows so the editor can choose which source/framing to use.
- Preserves the order of the Codex candidate list for the review shortlist.
- Uses `factual_basis` and `legal_sector_relevance_note` as the source-grounded context for final summaries and QA.

## Compliance-Safe Extraction

The collector:

- Respects `robots.txt`.
- Does not bypass paywalls.
- Uses RSS, public metadata, article headlines, dates, snippets, source descriptions, and links.
- Extracts full article text only where publicly accessible and permitted.
- Treats paywalled sources as metadata-only.
- Does not store full article text in issue archives, logs, or JSON outputs.

If a paywalled item does not provide enough accessible metadata to summarise accurately, it should be excluded unless another reliable accessible source supports it.

## Outputs

For each issue date, the generator creates:

- `issues/YYYY-MM-DD/issue.json`
- `issues/YYYY-MM-DD/issue.md`
- `issues/YYYY-MM-DD/issue.html`
- `issues/YYYY-MM-DD/issue.txt`
- `issues/YYYY-MM-DD/qa_report.md`
- `issues/YYYY-MM-DD/review_shortlist.json`
- `issues/YYYY-MM-DD/editorial_selection.md`

When using the Codex-assisted workflow, the human-prepared input file is:

- `issues/YYYY-MM-DD/candidates.json`

The canonical output is `issue.json`. HTML, Markdown, and plain text are rendered from the structured `Issue` object. Internal scores are stored in JSON for reviewability but are not rendered in the visible newsletter.

The review shortlist contains up to 30 relevant candidate stories from the 14-day window. `editorial_selection.md` uses Markdown checkboxes: tick 8-12 stories, then rerun the generator for the same date to rebuild the final issue files from the checked selection.

## Setup

Requirements:

- Python 3.11+
- OpenAI API key
- GitHub Actions enabled for manual PR generation

Install locally:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
```

On Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

## Configuration

Required for live generation:

- `OPENAI_API_KEY`
- `OPENAI_MODEL_HIGH_QUALITY`
- `OPENAI_MODEL_FAST`

Useful controls:

- `MAX_CANDIDATES=80`
- `MAX_SHORTLIST=40`
- `MAX_REVIEW_STORIES=30`
- `MAX_FINAL_STORIES=12`
- `MIN_FINAL_STORIES=8`
- `MAX_SOURCES_PER_STORY=3`
- `MAX_EXTRACT_CHARS_PER_ARTICLE=6000`
- `REQUIRE_HUMAN_REVIEW=true`
- `DRY_RUN_NO_AI=false`
- `ENABLE_OPENAI_WEB_SEARCH=false`
- `NEWSLETTER_NAME="The Irish Legal Innovator"`

Future beehiiv placeholders:

- `BEEHIIV_API_KEY`
- `BEEHIIV_PUBLICATION_ID`

Beehiiv values are not required for the MVP and are not validated as required settings.

Never commit `.env` or real secrets. GitHub Actions should read secrets from repository secrets or variables.

## Local Run

Generate locally without opening a PR:

```bash
python -m legal_innovator.main generate --no-pr
```

Use a reproducible run date:

```bash
python -m legal_innovator.main generate --run-date 2026-05-19 --no-pr
```

Override limits:

```bash
python -m legal_innovator.main generate --max-candidates 80 --max-review-stories 30 --max-final-stories 12 --no-pr
```

Generate from a Codex candidate file:

```bash
python -m legal_innovator.main generate --run-date 2026-05-24 --candidate-file issues/2026-05-24/candidates.json --no-pr
```

Rebuild the final issue from an edited checkbox selection:

```bash
python -m legal_innovator.main generate --run-date 2026-05-24 --candidate-file issues/2026-05-24/candidates.json --selection-file issues/2026-05-24/editorial_selection.md --no-pr
```

## GitHub Actions Manual Workflow

The manual workflow is [generate-newsletter.yml](.github/workflows/generate-newsletter.yml).

It:

1. Runs manually via `workflow_dispatch`.
2. Installs the package.
3. Uses `candidate_file` if supplied.
4. If `candidate_file` is blank, automatically uses `issues/YYYY-MM-DD/candidates.json` when that file exists.
5. Falls back to RSS/source discovery only when no candidate file is supplied or found.
6. Generates the issue files.
7. Updates `data/seen_urls.json` and `data/seen_story_clusters.json`.
8. Opens or updates a PR on `newsletter/YYYY-MM-DD`.

The PR title is:

`Draft issue: The Irish Legal Innovator - YYYY-MM-DD`

The workflow requests only:

```yaml
permissions:
  contents: write
  pull-requests: write
```

Repository settings may need Actions workflow permissions enabled so GitHub Actions can create pull requests.

Recommended GitHub process:

1. Save the Codex research output as `issues/YYYY-MM-DD/candidates.json`.
2. Commit and push that candidate file to `main`.
3. Run **Generate newsletter** in GitHub Actions with the same `run_date`.
4. Review the generated PR.
5. Edit `issues/YYYY-MM-DD/editorial_selection.md` on the PR branch to tick 8-12 stories.
6. Rerun **Generate newsletter** from the PR branch for the same `run_date`.
7. Review the rebuilt `issue.html`, `issue.md`, `issue.txt`, `issue.json`, and `qa_report.md`.
8. Merge the PR when approved.

## PR Review Workflow

The generated PR body includes:

- Issue summary
- Final story list
- Editorial selection shortlist
- Source links
- QA checklist
- Warning flags
- Confirmation that all stories are within the 14-day window
- Confirmation that every story has at least one reliable source
- Confirmation that visible scoring is not included
- Confirmation that opinion pieces and vendor-only announcements were excluded
- Confirmation that the disclaimer is included

Merging the PR archives the approved issue and repeat-prevention files in the repository. It does not publish or send anything.

For Beehiiv, use `issue.html` as the manual HTML source for the MVP. Future beehiiv integration should create a draft only after human approval and should never send automatically unless explicitly enabled.

## Archives and Repeat Prevention

The MVP uses repo-file storage:

- `data/seen_urls.json`
- `data/seen_story_clusters.json`
- `issues/`

Seen URLs and story fingerprints are updated on the PR branch so merged issues become the source of truth for repeat prevention.

## Ranking

Ranking is weighted, not section-based. The visible newsletter is one ranked list of 8-12 stories.

Internal scoring considers:

- Irish relevance, then UK/EU, then US/global
- Legal-sector relevance
- Innovation significance
- Practical impact for firms, departments, clients, courts, or regulators
- Source credibility
- Recency within the 14-day window
- Factual-news character
- Direct legal-sector specificity

Scores are never shown in HTML, Markdown, or plain text.

## OpenAI Usage

OpenAI assists with:

- Relevance classification for fallback RSS/source discovery
- Opinion/vendor-fluff exclusion for fallback RSS/source discovery
- Article clustering and deduplication for fallback RSS/source discovery
- Ranking inputs for fallback RSS/source discovery
- Neutral summaries
- One-sentence "Why it matters"
- Executive intro
- Factual QA against source snippets, metadata, and permitted text

When a Codex candidate file is supplied, the system skips broad live discovery and does not spend API credits searching or classifying the full web. OpenAI API usage is concentrated on final summaries, the executive intro, and factual QA for the selected issue.

To control cost, keep `ENABLE_OPENAI_WEB_SEARCH=false` for normal runs and use the Codex candidate-file workflow as the main collection layer. Increase `MAX_CANDIDATES` or enable OpenAI web search only when the shortlist is clearly missing important stories and you want a one-off expanded discovery run.

AI responses are requested as structured JSON and validated with Pydantic. If validation fails, the call is retried once with a corrective prompt. If it still fails, the failure is recorded in `qa_report.md` and affected items are excluded or safely handled.

## Adding Sources

Edit [data/sources.yaml](data/sources.yaml):

```yaml
- name: Example Legal Source
  url: https://example.com/feed
  type: rss
  region: uk_eu
  category: legaltech
  credibility: 0.75
  paywalled: false
  enabled: true
```

Supported source types are `rss`, `webpage`, and `sitemap` for the MVP. Prefer RSS feeds wherever possible. Search providers are intentionally adapter-based; OpenAI web search can be enabled for an expanded run, and a third-party news/search API can be added later without changing the rest of the pipeline.

## Reverting to Broader Discovery

If the lean workflow misses important stories, first try reversible configuration changes:

```bash
MAX_CANDIDATES=150
ENABLE_OPENAI_WEB_SEARCH=true
```

In GitHub Actions, set repository variable `ENABLE_OPENAI_WEB_SEARCH` to `true` and run the workflow with `maximum_candidates` set to `150`.

If you want to undo the lean-process code/docs change entirely, revert the commit that introduced it:

```bash
git revert <commit-sha>
git push
```

That creates a new commit restoring the previous behaviour without rewriting history.

## Future beehiiv Integration

The adapter boundary is in [src/legal_innovator/publishing.py](src/legal_innovator/publishing.py).

Future work should add:

- `Publisher` implementation for beehiiv.
- Draft creation only after PR approval or merge.
- Configuration that never sends automatically unless explicitly enabled.
- Clear separation from collection, ranking, summarisation, rendering, QA, and archive storage.

## Tests

Run deterministic tests:

```bash
python -m pytest
```

Tests mock the expensive and live-service boundaries by constructing typed objects directly. They do not call the OpenAI API or live news sources.

Current coverage checks include:

- Story-count and date-window validation
- Required source links and max three sources per story
- Hidden internal scores in visible renders
- Disclaimer rendering
- Duplicate story clustering fallback
- Archive JSON does not include full article text
- PR body generation
- Required OpenAI environment validation
- Beehiiv credentials are not required

## Troubleshooting

Missing OpenAI configuration:

- Set `OPENAI_API_KEY`, `OPENAI_MODEL_HIGH_QUALITY`, and `OPENAI_MODEL_FAST`.

No or too few stories:

- Check `qa_report.md` for source access, robots, extraction, classification, and OpenAI failures.
- If using the Codex-assisted workflow, check that `issues/YYYY-MM-DD/candidates.json` contains valid JSON and that candidate dates are inside the 14-day window.
- Check that candidate items intended to start ticked by default have `selected: true`.
- Review `data/sources.yaml` and add more high-quality RSS feeds or source pages.
- For a one-off expanded run, increase `MAX_CANDIDATES` and enable `ENABLE_OPENAI_WEB_SEARCH=true`.

Candidate file import fails:

- Ensure the file is a JSON array or an object with a `candidates` array.
- Ensure every item has the exact required fields listed in **Candidate File Format**.
- Ensure `source_url` values are direct `http` or `https` source URLs.
- Ensure `source_origin` uses one of the supported values.

GitHub Action cannot create a PR:

- Ensure repository Actions permissions allow workflows to create pull requests.
- Confirm the workflow has `contents: write` and `pull-requests: write`.

Paywalled source looks sparse:

- This is expected. The MVP only uses accessible metadata, snippets, dates, and links.

Rendered issue contains a factual warning:

- Review the source links and QA report before merging. The MVP is designed for human editorial approval.

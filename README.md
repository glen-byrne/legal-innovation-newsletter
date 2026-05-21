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

## Lean Fortnightly Workflow

The recommended low-cost workflow is:

1. Collect candidates from curated RSS feeds, public source pages, and sitemaps.
2. Apply deterministic filters first: date window, source validity, duplicate URLs, obvious opinion/commentary, vendor-only items, and broad irrelevant technology stories.
3. Use OpenAI only on the narrowed candidate pool for relevance classification, deduplication, ranking support, final summaries, and factual QA.
4. Generate a 25-30 story review shortlist.
5. Review `editorial_selection.md` and tick 8-12 stories.
6. Rerun the generator for the same issue date to rebuild the final issue from the selected stories.
7. Review the PR and merge only when the issue is editorially approved.

This workflow is designed to minimise API spend while preserving source traceability and human editorial control.

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

Rebuild the final issue from an edited checkbox selection:

```bash
python -m legal_innovator.main generate --run-date 2026-05-20 --selection-file issues/2026-05-20/editorial_selection.md --no-pr
```

## GitHub Actions Manual Workflow

The manual workflow is [generate-newsletter.yml](.github/workflows/generate-newsletter.yml).

It:

1. Runs manually via `workflow_dispatch`.
2. Installs the package.
3. Generates the issue files.
4. Updates `data/seen_urls.json` and `data/seen_story_clusters.json`.
5. Opens a PR on `newsletter/YYYY-MM-DD`.

The PR title is:

`Draft issue: The Irish Legal Innovator - YYYY-MM-DD`

The workflow requests only:

```yaml
permissions:
  contents: write
  pull-requests: write
```

Repository settings may need Actions workflow permissions enabled so GitHub Actions can create pull requests.

## PR Review Workflow

The generated PR body includes:

- Issue summary
- Final story list
- Source links
- QA checklist
- Warning flags
- Confirmation that all stories are within the 14-day window
- Confirmation that every story has at least one reliable source
- Confirmation that visible scoring is not included
- Confirmation that opinion pieces and vendor-only announcements were excluded
- Confirmation that the disclaimer is included

Merging the PR archives the approved issue and repeat-prevention files in the repository. It does not publish or send anything.

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

- Relevance classification
- Opinion/vendor-fluff exclusion
- Article clustering and deduplication
- Ranking inputs
- Neutral summaries
- One-sentence "Why it matters"
- Executive intro
- Factual QA against source snippets, metadata, and permitted text

To control cost, keep `ENABLE_OPENAI_WEB_SEARCH=false` for normal runs and use RSS/source discovery as the main collection layer. Increase `MAX_CANDIDATES` or enable OpenAI web search only when the shortlist is clearly missing important stories.

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
- Review `data/sources.yaml` and add more high-quality RSS feeds or source pages.
- For a one-off expanded run, increase `MAX_CANDIDATES` and enable `ENABLE_OPENAI_WEB_SEARCH=true`.

GitHub Action cannot create a PR:

- Ensure repository Actions permissions allow workflows to create pull requests.
- Confirm the workflow has `contents: write` and `pull-requests: write`.

Paywalled source looks sparse:

- This is expected. The MVP only uses accessible metadata, snippets, dates, and links.

Rendered issue contains a factual warning:

- Review the source links and QA report before merging. The MVP is designed for human editorial approval.

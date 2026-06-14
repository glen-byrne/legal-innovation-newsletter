# The Legal Edge Ireland

Lean MVP newsletter generation system for **The Legal Edge Ireland**, an executive-style legal innovation briefing.

The system discovers legal innovation news from the 14 days immediately before the run date, prioritises Irish relevance while allowing major UK/EU and global stories to outrank minor local items, and generates review-ready issue files for a human-approved GitHub pull request.

The MVP does **not** send email. Optional publisher adapters may create reviewable drafts, but sending remains manual.

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

The recommended low-cost workflow uses Codex for research discovery and the local dashboard for selection, rendering, and QA:

1. Prompt Codex to gather all materially relevant candidate stories using [docs/codex-news-scan-prompt.md](docs/codex-news-scan-prompt.md).
2. Save the Codex output as JSON at `issues/YYYY-MM-DD/candidates.json`.
3. Commit and push the candidate file so the repository archive stays current.
4. Open the dashboard with `start-dashboard.cmd`.
5. Open the latest issue in the dashboard. The library shows when `candidates.json` was last updated, which helps distinguish repeat scans on the same day.
6. Review the candidate stories and tick the items to include in the final newsletter. There is no upper cap on the number selected.
7. Click **Generate newsletter HTML**.
8. Copy the generated HTML into the mailing campaign platform, or use the optional Brevo draft button.
9. Review and send manually inside the mailing platform.

This workflow is designed to minimise API spend while preserving source traceability and human editorial control. The legacy RSS/source discovery path remains available as a fallback when no candidate file is supplied.

## Local Review Dashboard

The repository includes a local web dashboard for the editorial review workflow.

The dashboard can:

- List local issue folders as a newsletter library.
- Show how many candidate stories each issue contains.
- Show the last modified time of each `candidates.json` scan.
- Display candidate stories from `issues/YYYY-MM-DD/candidates.json` as selectable story cards.
- Save selections to `issues/YYYY-MM-DD/editorial_selection.md`.
- Generate `issue.html`, `issue.md`, `issue.txt`, `issue.json`, and `qa_report.md` locally.
- Show the generated HTML with a copy button and preview.
- Optionally create a Brevo draft campaign from the generated HTML when Brevo settings are configured.

The dashboard still uses the same source-of-truth files:

- Input candidates: `issues/YYYY-MM-DD/candidates.json`
- Human selection: `issues/YYYY-MM-DD/editorial_selection.md`
- Generated HTML: `issues/YYYY-MM-DD/issue.html`

Install the optional dashboard dependencies:

```bash
python -m pip install ".[dashboard]"
```

Run locally:

```bash
uvicorn legal_innovator.dashboard.app:app --reload
```

The easiest Windows launch path is:

```powershell
.\start-dashboard.cmd
```

For manual PowerShell startup:

```powershell
$env:DASHBOARD_ALLOW_NO_AUTH="true"
$env:DASHBOARD_COOKIE_SECURE="false"
uvicorn legal_innovator.dashboard.app:app --port 8002 --reload
```

For a hosted service such as Render or Railway, use:

- Build command: `python -m pip install ".[dashboard]"`
- Start command: `uvicorn legal_innovator.dashboard.app:app --host 0.0.0.0 --port $PORT`

For local use via `start-dashboard.cmd`, no dashboard password or GitHub token is required.

Required hosted dashboard environment variables:

- `DASHBOARD_GITHUB_REPOSITORY`, for example `glen-byrne/legal-innovation-newsletter`
- `DASHBOARD_GITHUB_TOKEN`
- `DASHBOARD_PASSWORD`

Optional dashboard environment variables:

- `DASHBOARD_BASE_BRANCH=main`
- `DASHBOARD_WORKFLOW_FILE=generate-newsletter.yml`
- `DASHBOARD_SECRET_KEY`
- `DASHBOARD_COOKIE_SECURE=true`
- `DASHBOARD_ALLOW_NO_AUTH=false`
- `DASHBOARD_AI_INTRO=true`, uses OpenAI to draft the issue overview when OpenAI settings are present

Use a fine-grained GitHub token with access only to this repository where possible. It needs repository contents read/write permission and permission to dispatch Actions workflows. Keep the hosted dashboard behind HTTPS and a strong password. Use `DASHBOARD_COOKIE_SECURE=false` only for local HTTP testing.

Optional Brevo draft-campaign environment variables:

- `BREVO_API_KEY`
- `BREVO_SENDER_NAME="The Legal Edge Ireland"`
- `BREVO_SENDER_EMAIL` or `BREVO_SENDER_ID`
- `BREVO_LIST_IDS`, comma-separated, for example `12` or `12,34`
- `BREVO_REPLY_TO`
- `BREVO_CAMPAIGN_TAG=legal-edge-ireland`

When these are present, the generated HTML page shows **Create Brevo draft**. The dashboard creates a draft campaign only. It does not call Brevo's send endpoints.

## Candidate File Format

For the automated pipeline, ask Codex to return JSON rather than only a visual table. The candidate file may be either a JSON array or an object with a `candidates` array.

Example:

```json
{
  "candidates": [
    {
      "id": "TLEI-2026-05-24-001",
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

The dashboard review shortlist shows all imported candidate stories from the 14-day window. Select the stories you want in the dashboard, then generate the final HTML from that selection.

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

- `MAX_CANDIDATES=0`
- `MAX_SHORTLIST=40`
- `MAX_REVIEW_STORIES=0`
- `MAX_FINAL_STORIES=0`
- `MIN_FINAL_STORIES=8`
- `MAX_SOURCES_PER_STORY=3`
- `MAX_EXTRACT_CHARS_PER_ARTICLE=6000`
- `REQUIRE_HUMAN_REVIEW=true`
- `DRY_RUN_NO_AI=false`
- `ENABLE_OPENAI_WEB_SEARCH=false`
- `NEWSLETTER_NAME="The Legal Edge Ireland"`

Future beehiiv placeholders:

- `BEEHIIV_API_KEY`
- `BEEHIIV_PUBLICATION_ID`

Beehiiv values are not required for the MVP and are not validated as required settings.

Optional Brevo values are also not required for generation. They are used only by the dashboard's draft-campaign button.

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

Override limits. A value of `0` means no cap:

```bash
python -m legal_innovator.main generate --max-candidates 0 --max-review-stories 0 --max-final-stories 0 --no-pr
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

`Draft issue: The Legal Edge Ireland - YYYY-MM-DD`

The workflow requests only:

```yaml
permissions:
  contents: write
  pull-requests: write
```

Repository settings may need Actions workflow permissions enabled so GitHub Actions can create pull requests.

Recommended GitHub process when using Actions rather than the local dashboard:

1. Save the Codex research output as `issues/YYYY-MM-DD/candidates.json`.
2. Commit and push that candidate file to `main`.
3. Run **Generate newsletter** in GitHub Actions with the same `run_date`.
4. Review the generated PR.
5. Edit `issues/YYYY-MM-DD/editorial_selection.md` on the PR branch to tick the stories you want.
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

Merging the PR archives the approved issue and repeat-prevention files in the repository. It does not send anything.

For Brevo, the dashboard can create a draft campaign from `issue.html` when Brevo settings are configured. For Beehiiv or other platforms, use `issue.html` as the manual HTML source unless a draft-only adapter is added.

## Archives and Repeat Prevention

The MVP uses repo-file storage:

- `data/seen_urls.json`
- `data/seen_story_clusters.json`
- `issues/`

Seen URLs and story fingerprints are updated on the PR branch so merged issues become the source of truth for repeat prevention.

## Ranking

Ranking is weighted, not section-based. The visible newsletter is one ranked list of the stories selected by the editor.

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

To control cost, keep `ENABLE_OPENAI_WEB_SEARCH=false` for normal runs and use the Codex candidate-file workflow as the main collection layer. Set a positive `MAX_CANDIDATES` value only when you deliberately want to cap fallback RSS/source discovery, or enable OpenAI web search for a one-off expanded run.

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
MAX_CANDIDATES=0
ENABLE_OPENAI_WEB_SEARCH=true
```

In GitHub Actions, set repository variable `ENABLE_OPENAI_WEB_SEARCH` to `true` and leave `maximum_candidates` as `0` for no cap, or set a positive number if you want a deliberate limit.

If you want to undo the lean-process code/docs change entirely, revert the commit that introduced it:

```bash
git revert <commit-sha>
git push
```

That creates a new commit restoring the previous behaviour without rewriting history.

## Publisher Integrations

The adapter boundary is in [src/legal_innovator/publishing.py](src/legal_innovator/publishing.py).

Implemented:

- `BrevoPublisher`, which creates draft email campaigns using the generated HTML.
- Dashboard button for creating a Brevo draft when Brevo settings are configured.

Future work may add:

- `Publisher` implementation for beehiiv if API access and HTML handling are suitable.
- Additional draft-only adapters for other newsletter platforms.
- Optional post-merge draft creation.
- Clear separation from collection, ranking, summarisation, rendering, QA, and archive storage.

## Tests

Run deterministic tests:

```bash
python -m pytest
```

Tests mock the expensive and live-service boundaries by constructing typed objects directly. They do not call the OpenAI API or live news sources.

Current coverage checks include:

- Story-presence and date-window validation
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
- For a one-off expanded run, enable `ENABLE_OPENAI_WEB_SEARCH=true` and leave `MAX_CANDIDATES=0` unless you want a deliberate cap.

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

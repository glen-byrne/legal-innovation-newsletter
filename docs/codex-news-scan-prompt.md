You are working inside the Git repository at C:\Users\Glen\Documents\legal-innovation-newsletter.

Your task is to find recent factual news items relevant to an executive briefing called The Legal Edge Ireland, then save the candidate list directly into the repository as valid JSON.

Set ISSUE_DATE to the current local date on the day this prompt is used, in YYYY-MM-DD format. Do not hard-code the issue date.

Set SCAN_DISPLAY_DATE to ISSUE_DATE formatted as DD/MM/YYYY.

Before starting the research task, determine SCAN_NUMBER for this date by counting existing git commits whose subject starts with `Add candidate stories for {ISSUE_DATE} issue`, then adding 1. If this cannot be determined reliably, use 1.

If Codex has access to a chat/thread title control, rename this chat to:

Scan {SCAN_DISPLAY_DATE} - {SCAN_NUMBER}

If Codex cannot rename the chat automatically, include this exact suggested chat title in your final reply.

Create this folder if it does not already exist:

issues/{ISSUE_DATE}/

Save the final candidate list as:

issues/{ISSUE_DATE}/candidates.json

After saving the file, commit and push it with a commit message like:

Add candidate stories for {ISSUE_DATE} issue

Do not generate the final newsletter. Do not edit issue.md, issue.html, issue.txt, issue.json, qa_report.md, review_shortlist.json, or editorial_selection.md. Only create or update candidates.json.

Research task:

Find recent factual news items published within the last 14 days before ISSUE_DATE.

Return up to this many candidate stories: 50

Prioritise quality over quantity. Do not pad the list with weak, generic, duplicative, or only loosely relevant items.

When verifying source URLs, batch source checks where possible and avoid asking for separate approvals for each individual URL. Prefer built-in web/search/browser tools over PowerShell Invoke-WebRequest where available.

Prioritise stories about innovation in the practice, delivery, management, engineering, design, and business of law. Give stronger weight to stories involving legal technology, legal AI, workflow engineering, service design, court digitisation, access-to-justice tools, legal operations, knowledge systems, document systems, e-discovery, CLM, matter management, legal education technology, AI governance for lawyers, and new legal-service delivery models.

Prioritise:

1. Irish and all-island legal innovation news.
2. UK and EU legal innovation developments.
3. Major US or global stories where they are materially relevant to law firms, legal departments, courts, regulators, legal services, clients, or the legal market.

Demote generic legal, regulatory, litigation, policy, or business stories unless they clearly affect how legal work is produced, delivered, governed, priced, taught, accessed, supervised, automated, or transformed.

Exclude:

- opinion pieces
- commentary
- podcasts
- advertorials
- generic vendor marketing
- minor product launches
- stories based only on search-result snippets or headlines
- items without direct source URLs
- generic technology regulation without a clear legal-practice, legal-market, or legal-service-delivery angle

The saved file must be valid JSON only. Do not wrap it in Markdown fences. Do not include comments. Use exactly this top-level structure:

{ "candidates": [] }

Each candidate must include exactly these fields:

- id
- headline
- published_date
- source_name
- source_url
- event_type
- source_origin
- region
- factual_basis
- legal_sector_relevance_note
- duplicate_group
- warning_flags
- selected

Field rules:

id: stable sequential identifier using ISSUE_DATE, e.g. TLEI-{ISSUE_DATE}-001

headline: story headline

published_date: publication date in YYYY-MM-DD format

source_name: name of the publication, organisation, court, regulator, company, or official body

source_url: direct source URL to the article, press release, report, judgment, consultation, or source document

event_type: one of court_digitisation, legal_ai_adoption, legal_tech_product, professional_guidance, regulatory_development, access_to_justice, legal_education, legal_operations, funding_acquisition_partnership, reported_platform_entry, or other

source_origin: one of official_source, confirmed_reporting, reported_not_officially_confirmed, secondary_reporting, or vendor_originated_announcement

region: one of Ireland, UK/EU, US/global, or global

factual_basis: short source-grounded snippet explaining the concrete factual basis for inclusion

legal_sector_relevance_note: brief note explaining why the story matters to legal-sector readers, with emphasis on legal innovation, technology, workflow, engineering, design, delivery, operations, courts, access to justice, or legal-market impact

duplicate_group: identifier grouping duplicate or closely related reports of the same underlying development, e.g. DG-001; use none if no duplicate relationship is apparent

warning_flags: an array of caveats such as paywalled, reported_not_confirmed, vendor_originated, limited_detail, possible_duplicate, or date_uncertain; use an empty array if there are no warnings

selected: true if the item is recommended for editorial consideration; false only if included for transparency as a near-miss, duplicate, or cautionary item

Final quality check before saving:

- the date window has been applied consistently
- Irish and all-island stories have been prioritised where available
- legal-innovation stories are prioritised over general legal/regulatory news
- each item has a direct source URL
- each item has a clear factual basis
- vendor-originated stories are labelled appropriately
- duplicate groups are used consistently
- JSON is valid and parseable

After writing the file, run a JSON parse check if possible.

Then run:

git add issues/{ISSUE_DATE}/candidates.json
git commit -m "Add candidate stories for {ISSUE_DATE} issue"
git push

After pushing, reply briefly with:

- the number of candidate stories saved
- the path of the saved file
- the commit hash if available
- any warnings or caveats
```

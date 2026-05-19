from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from legal_innovator.config import RunWindow, Settings
from legal_innovator.discovery import DiscoveryService, SourceConfig
from legal_innovator.models import Region, Source, SourceType


def test_webpage_discovery_skips_javascript_links() -> None:
    html = """
    <html>
      <body>
        <article>
          <a href="javascript:void(0);">Menu toggle link that must be ignored</a>
          <time datetime="2026-05-18T09:00:00+01:00">18 May 2026</time>
        </article>
        <article>
          <a href="/valid-legal-ai-story">Irish law firm adopts AI governance tooling</a>
          <time datetime="2026-05-18T10:00:00+01:00">18 May 2026</time>
          <p>A dated legal technology news item.</p>
        </article>
      </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = Settings(dry_run_no_ai=True)
    run_at = datetime(2026, 5, 19, 12, 0, tzinfo=ZoneInfo("Europe/Dublin"))
    window = RunWindow(run_at=run_at, start_at=run_at - timedelta(days=14), end_at=run_at)
    service = DiscoveryService(settings, client=client)
    config = SourceConfig(
        sources=[
            Source(
                name="Example Source",
                url="https://example.com/news",
                type=SourceType.WEBPAGE,
                region=Region.IRELAND,
            )
        ],
        queries=[],
    )

    candidates = service.collect(config, window)

    assert len(candidates) == 1
    assert str(candidates[0].url) == "https://example.com/valid-legal-ai-story"
    assert not service.errors

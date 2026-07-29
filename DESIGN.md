# DESIGN — adding a new county adapter

The framework is built so that **the only thing that varies between counties is
parsing**. The crawl orchestration, case-number generation, HTTP concerns,
pipeline, and CSV contract are all shared. Adding a county is therefore mostly a
*configuration* exercise, plus a small adapter class if the site's markup is
genuinely new.

## The two moving parts

1. **A YAML config** in `config/` — base URL, CSS selectors, and the
   case-number sequences.
2. **An adapter class** — a subclass of `BaseScraper` that implements six hooks.
   If the new portal looks like one you already support (an ASP.NET grid or a
   JS-rendered DOM), you often subclass the existing adapter and override one or
   two methods instead of writing a new one.

## `BaseScraper` contract

`BaseScraper` is a *template method*: `scrape()` fixes the flow and calls these
hooks, which each adapter implements:

| Hook | Returns | Purpose |
| --- | --- | --- |
| `search_page_urls()` | `Iterator[str]` | URLs of each results page (pagination) |
| `parse_search_results(html)` | `list[str]` | case references on a results page |
| `build_case_url(ref)` | `str` | detail-page URL for one case |
| `parse_case_header(html, ref)` | `dict[str, str]` | scalar case fields |
| `parse_parties(html)` | `list[Party]` | parties + their attorneys |
| `parse_events(html)` | `list[Event]` | docket events / hearings |

`parse_case()` (concrete, in the base) stitches header + parties + events into a
`Case`. You never touch the pipeline, CSV columns, dedup, rate limiting,
retries, checkpointing, or logging.

## The ~20-line adapter

If "Dallas County" runs the same ASP.NET Public Access software as Travis, the
adapter is essentially:

```python
# src/court_scraper/adapters/dallas.py
from court_scraper.adapters.travis import TravisPublicAccessScraper

class DallasPublicAccessScraper(TravisPublicAccessScraper):
    """Dallas uses the same ASP.NET grid; only the selectors differ,
    and those live in the YAML config — so no method overrides are needed."""
```

Register it once:

```python
# src/court_scraper/adapters/__init__.py
register_adapter("dallas_public_access", DallasPublicAccessScraper)
```

…and add the config:

```yaml
# config/dallas_county.yaml
key: dallas
county: Dallas County
adapter: dallas_public_access
base_url: https://example-portal.invalid/dallas
court: 44th District Court
fixtures_dir: fixtures/dallas
selectors:
  search_result_link: "table#grdResults a.docket-link"
  header_row: "#summary tr"
  party_row: "table#grdParties tr.data"
  event_row: "table#grdDocket tr.data"
search_pages: [results_1]
sequences:
  - pattern: plain
    template: "DC-{year}-{seq}{suffix}"
    extra: { year: "24" }
    start: 1
    end: 500
    width: 5
```

That's a new county: **one tiny class + one YAML file.** Because the selectors
are config, even the class is often unnecessary — you can point the existing
`aspnet_public_access` adapter at Dallas purely via YAML.

## When you *do* need to override

Write a real method override only when the site deviates structurally, e.g.:

- Names come pre-split into separate columns → override `parse_parties` to read
  the columns directly instead of calling `split_name`.
- Events live in a JSON blob embedded in a `<script>` tag → override
  `parse_events` to parse the JSON.
- Pagination is a "next" cursor rather than numbered pages → override
  `search_page_urls` to follow the cursor.

Everything else stays inherited.

## Swapping the fetcher (e.g. Playwright)

Adapters depend only on the `Fetcher` protocol (`get(url) -> str`). To scrape a
JS portal live, implement a `PlaywrightFetcher` that renders the page and returns
`page.content()`, then pass it in place of `FixtureFetcher`/`HttpFetcher`. No
adapter or pipeline code changes — the parsing already targets the rendered DOM.

## Testing a new adapter

1. Drop a synthetic search page and a couple of case pages under
   `fixtures/<key>/`, covering your edge cases (0 / 1 / many attorneys).
2. Add a config fixture-mode test mirroring `tests/test_parsers.py`.
3. Run `pytest`. The shared pipeline and generator tests already cover the rest.

# Texas Court Records Scraper

A portfolio-grade, **config-driven web-scraping & data-engineering framework**
that extracts civil court **case + attorney** data from multiple county court
portals and outputs a single normalized CSV (one row per attorney).

It ships as a **fully offline demo**: the scrapers run against synthetic HTML
**fixtures** that model two very different portal styles, so you can clone the
repo and see the whole pipeline work end-to-end with no network access and no
contact with any real government website.

> ⚖️ **This project never scrapes a live site.** See
> [Legal & Ethical Considerations](#legal--ethical-considerations).

---

## Why it's interesting

| Concern | How it's handled |
| --- | --- |
| **Many different portals** | An abstract `BaseScraper` fixes the crawl flow; per-county adapters override only the site-specific parsing. |
| **Two portal *technologies*** | One adapter models a classic **ASP.NET "Public Access"** WebForms grid; the other models a **JavaScript SPA** (parsed post-render, so a Playwright driver slots straight in). |
| **Messy case-number schemes** | A dedicated `CaseNumberGenerator` models plain ranges, letter-suffix permutations (A–H), and independent per-suffix numbering. |
| **Dirty data** | Name splitting (`Smith, John Q. Jr.` → parts), date normalization, "stacked" date/location cells, whitespace collapse, and row de-duplication. |
| **Long crawls** | Rate limiting, exponential-backoff retry, a pluggable proxy-rotation interface, structured JSON logging, and checkpoint/resume. |
| **Trust** | Type hints throughout, a `pytest` suite, and clean `src/` packaging. |

---

## Architecture

```mermaid
flowchart TD
    CFG[County YAML config<br/>base URL · selectors · sequences] --> ADP
    subgraph Scraper[BaseScraper &lt;template method&gt;]
        direction TB
        S1[search_page_urls] --> S2[parse_search_results]
        S2 --> S3[build_case_url]
        S3 --> S4[parse_case]
        S4 --> S4a[parse_case_header]
        S4 --> S4b[parse_parties + attorneys]
        S4 --> S4c[parse_events]
    end
    ADP[County adapter<br/>ASP.NET | JS portal] -->|implements hooks| Scraper
    FET[Fetcher<br/>FixtureFetcher · HttpFetcher · &lpar;Playwright&rpar;] --> Scraper
    Scraper -->|Case objects| PIPE[CasePipeline<br/>explode → normalize → dedup]
    PIPE --> CSV[(cases.csv<br/>14 columns · 1 row / attorney)]
```

Plain-text view of the same flow:

```
 county.yaml ─▶ Adapter(BaseScraper) ◀─ Fetcher (fixtures | http | playwright)
                     │
        search ─▶ paginate ─▶ open case ─▶ parse case
                                            ├─ header  (number, style, filed, type…)
                                            ├─ parties ─▶ attorneys (name split)
                                            └─ events / hearings (stacked cells)
                     │
                 Case objects
                     │
        CasePipeline: explode (1 row / attorney) ─▶ normalize ─▶ dedup
                     │
                 cases.csv  (exactly 14 columns)
```

### Package layout

```
texas-court-records-scraper/
├── config/                    # one YAML per county (URL, selectors, sequences)
│   ├── travis_county.yaml     #   ASP.NET Public Access portal
│   └── harris_county.yaml     #   JavaScript SPA portal
├── fixtures/                  # synthetic HTML the demo runs against (offline)
│   ├── travis/                #   search page + 4 case pages (0/1/5-attorney, stacked)
│   └── harris/                #   2 paginated search pages + 4 case pages
├── src/court_scraper/
│   ├── base.py                # BaseScraper abstract template method
│   ├── models.py              # Case / Party / Attorney / Event dataclasses
│   ├── case_numbers.py        # CaseNumberGenerator (the sequence highlight)
│   ├── parsing.py             # name split, date normalize, stacked-cell split
│   ├── config.py              # YAML loader
│   ├── http_client.py         # Fetcher protocol, rate limit, retry, proxy stub
│   ├── checkpoint.py          # progress/resume
│   ├── pipeline.py            # pandas explosion → CSV
│   ├── logging_config.py      # structured JSON logging
│   ├── cli.py                 # command-line entry point
│   └── adapters/
│       ├── travis.py          # ASP.NET adapter
│       └── harris.py          # JS-portal adapter
└── tests/                     # pytest: generator, parsers, pipeline, e2e
```

---

## How to run

Requires Python 3.9+.

```bash
# 1. Create a virtual environment and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Run the offline demo across both counties → output/cases.csv
court-scraper --config-dir config --fixtures --out output/cases.csv

# 3. Preview the case-number generator (no scraping)
court-scraper --config config/harris_county.yaml --list-case-numbers

# 4. Run the tests
pytest
```

> If `pip install -e` is unavailable on an older pip, you can run everything
> with `PYTHONPATH=src python -m court_scraper.cli ...` and `PYTHONPATH=src pytest`.

The `--live` flag exists and is wired to a rate-limited, retrying HTTP client,
but the demo and tests only ever use `--fixtures`. The config `base_url`s point
at a non-routable `.invalid` domain by design.

---

## Sample output

Running the demo writes a 14-column CSV. Columns (exact order):

```
County, Case Number, Case Name, Filing Date, Type, Status, Court,
First Name, Middle Name, Last Name, Suffix, Party (Plaintiff/Defendant),
Events / Hearings, Events / Hearings (cont.)
```

A few representative rows (abridged):

| County | Case Number | First | Middle | Last | Suffix | Party | Events / Hearings |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Travis County | D-1-GN-24-000001 | John | Q. | Smith | Jr. | Plaintiff | 2024-04-02 — Initial Case Management Hearing [Courtroom 3A] |
| Travis County | D-1-GN-24-000002 | | | | | | 2024-03-01 — Application for Letters Testamentary [Probate Annex, Room 210] |
| Harris County | 2024-CV-01003C | Daniel | | O'Sullivan | III | Defendant | 2024-04-01 — Expert Report Deadline |

Note the **0-attorney case** (`…000002`) still produces one row with blank name
fields — the case is never silently dropped — and suffixes (`Jr.`, `III`) are
lifted out of the name into their own column.

---

## Adding a new county

See [`DESIGN.md`](DESIGN.md) — a new adapter that reuses one of the two parsing
styles is roughly **20 lines plus a YAML file**.

---

## Legal & Ethical Considerations

This repository is a **software-engineering demonstration**, not a tool for
harvesting live court data. Please read this section before adapting it.

- **Runs on synthetic data only.** Every HTML file under `fixtures/` is
  hand-authored mock data. It contains **no real case records and no real
  personal data**. Case numbers, names, and events are invented. The configured
  `base_url`s use the reserved, non-routable `.invalid` TLD so the framework
  cannot accidentally contact a real host in fixture mode.
- **Public records are not unrestricted.** U.S. court records are often public,
  but county portals commonly impose **Terms of Service**, and bulk/automated
  access is frequently restricted or requires a separate data agreement. Public
  availability of a record does not by itself grant permission to scrape a site.
- **Respect `robots.txt` and Terms of Service.** Before pointing any adapter at
  a real portal you must review that site's `robots.txt` and ToS and obtain
  permission where required. This project does not encourage or condone
  violating them.
- **Rate limiting is on by default.** The live HTTP client is rate limited and
  uses exponential backoff so it degrades gracefully and does not hammer a
  server. The proxy-rotation interface is a **documented stub** — it exists to
  show the architecture, not to evade blocking.
- **Privacy.** Court data can include sensitive personal information. Any real
  use should minimize collection, follow applicable privacy law, and avoid
  republishing personal data.

In short: the value here is the **architecture, parsing, and data-engineering
craft**, demonstrated safely against fixtures. Adapting it to a live site is the
user's responsibility and must be done lawfully and with permission.

---

## License

[MIT](LICENSE)

# Project Overview — Texas Court Records Scraper

A one-page tour of this project: what it does, how it's built, and where things
live. For setup/run steps see [`README.md`](README.md); for how to add a new
county see [`DESIGN.md`](DESIGN.md).

---

## 1. What this project is

A **config-driven web-scraping & data-engineering framework** that extracts civil
court **case + attorney** data from multiple county court portals and outputs a
single normalized CSV (one row per attorney). It's a **software-engineering
demonstration** that runs entirely offline against synthetic HTML fixtures — it
never contacts a real government website.

- **Type:** data engineering / web scraping (production-style architecture)
- **Stack:** Python (abstract base class + per-county adapters, pandas pipeline,
  pytest) · YAML config
- **Author:** Muhammad Nasiruddin

## 2. How it works

```
county.yaml ─▶ Adapter(BaseScraper) ◀─ Fetcher (fixtures | http | playwright)
                     │
        search ─▶ paginate ─▶ open case ─▶ parse case
                                            ├─ header  (number, style, filed…)
                                            ├─ parties ─▶ attorneys (name split)
                                            └─ events / hearings (stacked cells)
                     │
                 Case objects
                     │
        CasePipeline: explode (1 row / attorney) ─▶ normalize ─▶ dedup
                     │
                 cases.csv  (exactly 14 columns)
```

- **`BaseScraper`** fixes the crawl flow as a template method; per-county
  **adapters** override only the site-specific parsing.
- Two portals are modelled fully: a classic **ASP.NET "Public Access"** grid
  (Travis) and a **JavaScript SPA** (Harris) — structured so a Playwright driver
  slots straight in.
- **`CaseNumberGenerator`** models the messy sequence schemes: plain ranges,
  letter-suffix permutations (A–H), and independent per-suffix numbering.
- The **pandas pipeline** explodes each case into one row per attorney and writes
  the exact 14-column CSV, after date/whitespace normalization and de-duplication.

## 3. Engineering quality

- Config-driven (one YAML per county), rate limiting, exponential-backoff retry,
  a pluggable proxy-rotation interface (documented stub), structured JSON
  logging, and checkpoint/resume for long crawls.
- Type hints throughout, `src/` packaging, and a **pytest suite of 36 tests**
  covering the generator, the parsers (against fixtures), and the
  attorney-explosion logic.

## 4. What's in the repo

| Path | What it is |
|------|------------|
| `src/court_scraper/base.py` | Abstract `BaseScraper` template method |
| `src/court_scraper/adapters/` | Travis (ASP.NET) + Harris (JS) adapters |
| `src/court_scraper/case_numbers.py` | The case-number sequence generator |
| `src/court_scraper/parsing.py` | Name split, date normalize, stacked-cell split |
| `src/court_scraper/pipeline.py` | pandas explosion → 14-column CSV |
| `src/court_scraper/http_client.py` | Fetcher protocol, rate limit, retry, proxy stub |
| `src/court_scraper/checkpoint.py` | Progress / resume |
| `src/court_scraper/cli.py` | Command-line entry point |
| `config/` | One YAML per county |
| `fixtures/` | Synthetic offline HTML (edge cases: 0 / 1 / 5 attorneys, stacked) |
| `tests/` | pytest suite (generator, parsers, pipeline, end-to-end) |

## 5. How to run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
court-scraper --config-dir config --fixtures --out output/cases.csv   # offline demo
pytest                                                                 # 36 tests
```

## 6. Skills this project demonstrates

Object-oriented design (template method + adapters) · HTML parsing & messy-data
normalization · pandas data pipelines · config-driven systems · resilient
crawling (rate limit / retry / resume) · testing with fixtures · clean packaging
and documentation · and a considered approach to the **legal & ethical** side of
scraping (see the README).

---

*Part of my portfolio, alongside data-science projects in customer segmentation
(clustering), churn prediction (classification), and retail-sales forecasting
(time series).*

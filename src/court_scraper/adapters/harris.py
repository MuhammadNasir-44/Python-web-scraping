"""Harris County adapter — JavaScript single-page portal.

Modern county portals render case data client-side from a JSON API. In
production the :class:`court_scraper.http_client.Fetcher` for this adapter would
be a Playwright-backed driver that loads the page, waits for the results to
render, and returns ``page.content()`` — the adapter's parsing code below is
written against that *rendered* DOM and would not change.

    ┌─────────────────────┐     rendered HTML     ┌──────────────────────┐
    │  PlaywrightFetcher  │ ────────────────────▶ │ HarrisJsPortalScraper │
    │ (drives JS, waits)  │                       │  (parses the DOM)     │
    └─────────────────────┘                       └──────────────────────┘

To keep the demo dependency-free and offline, the fixtures are pre-rendered
snapshots of what that driver would return, and the default fetcher is the
:class:`court_scraper.http_client.FixtureFetcher`. A ``PlaywrightFetcher`` would
slot in with no change to this class.
"""

from __future__ import annotations

from collections.abc import Iterator

from bs4 import BeautifulSoup

from court_scraper.base import BaseScraper
from court_scraper.models import Attorney, Event, Party
from court_scraper.parsing import (
    clean_text,
    is_non_attorney,
    normalize_date,
    split_name,
    split_stacked_cell,
)


class HarrisJsPortalScraper(BaseScraper):
    """Adapter for a JS-rendered portal (parsed post-render)."""

    def _sel(self, name: str, default: str) -> str:
        return str(self.config.selectors.get(name, default))

    @staticmethod
    def _soup(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    # ------------------------------------------------------------------ #
    # Search / pagination
    # ------------------------------------------------------------------ #
    def search_page_urls(self) -> Iterator[str]:
        # A live SPA route would be "#/search/<page>", but the fragment carries
        # no server path; the driver resolves each page to a real request URL.
        pages = self.config.extra.get("search_pages", ["results_1"])
        for page in pages:
            yield f"{self.config.base_url}/Search/{page}"

    def parse_search_results(self, html: str) -> list[str]:
        soup = self._soup(html)
        card_sel = self._sel("search_result_card", "div.result-card[data-case-number]")
        refs: list[str] = []
        for card in soup.select(card_sel):
            ref = clean_text(card.get("data-case-number", ""))
            if ref:
                refs.append(ref)
        return refs

    def build_case_url(self, case_ref: str) -> str:
        return f"{self.config.base_url}/Case/{case_ref}"

    # ------------------------------------------------------------------ #
    # Detail parsing
    # ------------------------------------------------------------------ #
    def parse_case_header(self, html: str, case_ref: str) -> dict[str, str]:
        soup = self._soup(html)
        root = soup.select_one(self._sel("case_root", "div.case-detail"))
        if root is None:
            return {"case_number": case_ref, "court": self.config.court}

        case_number = clean_text(root.get("data-case-number", "")) or case_ref
        style_el = root.select_one(self._sel("case_style", "h1.case-style"))
        case_name = clean_text(style_el.get_text()) if style_el else ""

        # Metadata is a definition list: <dt>Filed</dt><dd>...</dd>
        meta: dict[str, str] = {}
        meta_sel = self._sel("case_meta", "dl.case-meta")
        meta_dl = root.select_one(meta_sel)
        if meta_dl:
            terms = meta_dl.find_all("dt")
            defs = meta_dl.find_all("dd")
            for term, definition in zip(terms, defs):
                meta[clean_text(term.get_text()).lower()] = clean_text(definition.get_text())

        return {
            "case_number": case_number,
            "case_name": case_name,
            "filing_date": normalize_date(meta.get("filed", meta.get("date filed", ""))),
            "case_type": meta.get("type", meta.get("case type", "")),
            "status": meta.get("status", ""),
            "court": meta.get("court", self.config.court),
        }

    def parse_parties(self, html: str) -> list[Party]:
        soup = self._soup(html)
        party_sel = self._sel("party_block", "section.parties div.party")
        name_sel = self._sel("party_name", "span.party-name")
        role_attr = self._sel("party_role_attr", "data-role")
        attorney_sel = self._sel("attorney_item", "ul.attorneys li")

        parties: list[Party] = []
        for block in soup.select(party_sel):
            name_el = block.select_one(name_sel)
            name = clean_text(name_el.get_text()) if name_el else ""
            role = clean_text(block.get(role_attr, ""))
            attorneys: list[Attorney] = []
            for item in block.select(attorney_sel):
                text = clean_text(item.get_text())
                if is_non_attorney(text):
                    continue
                attorney = split_name(text)
                if not attorney.is_empty():
                    attorneys.append(attorney)
            parties.append(Party(name=name, role=role, attorneys=attorneys))
        return parties

    def parse_events(self, html: str) -> list[Event]:
        soup = self._soup(html)
        event_sel = self._sel("event_block", "section.events div.event")
        date_sel = self._sel("event_date", "span.event-date")
        desc_sel = self._sel("event_desc", "span.event-desc")
        loc_sel = self._sel("event_loc", "span.event-loc")

        events: list[Event] = []
        for block in soup.select(event_sel):
            date_el = block.select_one(date_sel)
            desc_el = block.select_one(desc_sel)
            loc_el = block.select_one(loc_sel)

            location = clean_text(loc_el.get_text()) if loc_el else ""
            raw_date = date_el.get_text("\n") if date_el else ""
            date, stacked_loc = split_stacked_cell(raw_date)
            # Some events stack date + location in the date node (no separate
            # location element); prefer the explicit element when present.
            if not location:
                location = stacked_loc

            events.append(
                Event(
                    date=normalize_date(date),
                    description=clean_text(desc_el.get_text()) if desc_el else "",
                    location=location,
                )
            )
        return events

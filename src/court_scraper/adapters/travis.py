"""Travis County adapter — classic ASP.NET "Public Access" form site.

This models the long-lived ASP.NET WebForms style of court portal: server-
rendered HTML with ``<table>`` grids (often ``id="grd..."``), label/value header
rows, and event grids that stack a date and a location into a single cell using
``<br>``.

Parsing is driven by CSS selectors read from the county YAML config, so the same
class can serve other ASP.NET portals with only a config change.
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


class TravisPublicAccessScraper(BaseScraper):
    """Adapter for an ASP.NET PublicAccess-style portal."""

    def _sel(self, name: str, default: str) -> str:
        return str(self.config.selectors.get(name, default))

    @staticmethod
    def _soup(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    @staticmethod
    def _cell_lines(cell) -> str:  # type: ignore[no-untyped-def]
        """Text of a cell with ``<br>`` rendered as newlines (for stacked cells)."""
        return cell.get_text("\n")

    # ------------------------------------------------------------------ #
    # Search / pagination
    # ------------------------------------------------------------------ #
    def search_page_urls(self) -> Iterator[str]:
        # A real crawl would POST the ASP.NET search form and follow __doPostBack
        # pagination. Offline, the config lists the pre-rendered results pages.
        pages = self.config.extra.get("search_pages", ["results_1"])
        for page in pages:
            yield f"{self.config.base_url}/Search/{page}"

    def parse_search_results(self, html: str) -> list[str]:
        soup = self._soup(html)
        link_sel = self._sel("search_result_link", "table#grdCases a.case-link")
        refs: list[str] = []
        for anchor in soup.select(link_sel):
            ref = clean_text(anchor.get_text())
            if ref:
                refs.append(ref)
        return refs

    def build_case_url(self, case_ref: str) -> str:
        # Case reference placed in the path so both live requests and the
        # fixture fetcher resolve to a stable, unique target.
        return f"{self.config.base_url}/Case/{case_ref}"

    # ------------------------------------------------------------------ #
    # Detail parsing
    # ------------------------------------------------------------------ #
    def parse_case_header(self, html: str, case_ref: str) -> dict[str, str]:
        soup = self._soup(html)
        header_sel = self._sel("header_row", "#caseHeader tr")
        fields: dict[str, str] = {}
        for row in soup.select(header_sel):
            label_el = row.select_one("td.label, th")
            value_el = row.select_one("td.value")
            if not label_el or not value_el:
                continue
            label = clean_text(label_el.get_text()).rstrip(":").lower()
            value = clean_text(value_el.get_text())
            fields[label] = value

        return {
            "case_number": fields.get("case number", case_ref),
            "case_name": fields.get("style", fields.get("case name", "")),
            "filing_date": normalize_date(fields.get("date filed", fields.get("filed", ""))),
            "case_type": fields.get("case type", fields.get("type", "")),
            "status": fields.get("status", ""),
            "court": fields.get("court", self.config.court),
        }

    def parse_parties(self, html: str) -> list[Party]:
        soup = self._soup(html)
        row_sel = self._sel("party_row", "table#grdParties tr.party-row")
        parties: list[Party] = []
        for row in soup.select(row_sel):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            name = clean_text(cells[0].get_text())
            role = clean_text(cells[1].get_text())
            attorneys: list[Attorney] = []
            # The attorney cell may stack multiple attorneys via <br>.
            for line in self._cell_lines(cells[2]).split("\n"):
                line = clean_text(line)
                if line and not is_non_attorney(line):
                    attorney = split_name(line)
                    if not attorney.is_empty():
                        attorneys.append(attorney)
            parties.append(Party(name=name, role=role, attorneys=attorneys))
        return parties

    def parse_events(self, html: str) -> list[Event]:
        soup = self._soup(html)
        row_sel = self._sel("event_row", "table#grdEvents tr.event-row")
        events: list[Event] = []
        for row in soup.select(row_sel):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            # First cell stacks date + location; second is the description.
            date, location = split_stacked_cell(self._cell_lines(cells[0]))
            description = clean_text(cells[1].get_text())
            events.append(
                Event(
                    date=normalize_date(date),
                    description=description,
                    location=location,
                )
            )
        return events

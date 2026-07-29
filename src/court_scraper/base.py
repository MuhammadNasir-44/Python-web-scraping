"""The abstract scraper defining the common crawl flow.

``BaseScraper`` is a *template method*: it fixes the sequence of steps that every
county crawl follows and delegates the site-specific parsing to abstract methods
that each adapter overrides.

    search  →  paginate  →  open case  →  parse case
                                          ├─ parse header
                                          ├─ parse parties (+ attorneys)
                                          └─ parse events / hearings
                                          →  yield Case

Concrete adapters implement five hooks:

* :meth:`search_page_urls`   – yields each search-results URL (pagination)
* :meth:`parse_search_results` – case references found on a results page
* :meth:`build_case_url`      – detail-page URL for a case reference
* :meth:`parse_case_header`   – the case's scalar fields
* :meth:`parse_parties`       – parties and their attorneys
* :meth:`parse_events`        – docket events / hearings
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from court_scraper.checkpoint import Checkpoint
from court_scraper.config import CountyConfig
from court_scraper.http_client import Fetcher
from court_scraper.logging_config import get_logger
from court_scraper.models import Case, Event, Party

logger = get_logger(__name__)


class BaseScraper(ABC):
    """Common crawl orchestration shared by all county adapters."""

    def __init__(
        self,
        config: CountyConfig,
        fetcher: Fetcher,
        checkpoint: Checkpoint | None = None,
    ):
        self.config = config
        self.fetcher = fetcher
        self.checkpoint = checkpoint

    # ------------------------------------------------------------------ #
    # Abstract, site-specific hooks
    # ------------------------------------------------------------------ #
    @abstractmethod
    def search_page_urls(self) -> Iterator[str]:
        """Yield the URL of each search-results page (handles pagination)."""

    @abstractmethod
    def parse_search_results(self, html: str) -> list[str]:
        """Return case references (e.g. case numbers) listed on a results page."""

    @abstractmethod
    def build_case_url(self, case_ref: str) -> str:
        """Build the detail-page URL for a single case reference."""

    @abstractmethod
    def parse_case_header(self, html: str, case_ref: str) -> dict[str, str]:
        """Return the case's scalar fields.

        Expected keys: ``case_number``, ``case_name``, ``filing_date``,
        ``case_type``, ``status``, ``court``.
        """

    @abstractmethod
    def parse_parties(self, html: str) -> list[Party]:
        """Return the parties (with their attorneys) for a case detail page."""

    @abstractmethod
    def parse_events(self, html: str) -> list[Event]:
        """Return the docket events / hearings for a case detail page."""

    # ------------------------------------------------------------------ #
    # Concrete template method
    # ------------------------------------------------------------------ #
    def parse_case(self, html: str, case_ref: str) -> Case:
        """Assemble a :class:`Case` from header + parties + events."""
        header = self.parse_case_header(html, case_ref)
        return Case(
            county=self.config.county,
            case_number=header.get("case_number", case_ref),
            case_name=header.get("case_name", ""),
            filing_date=header.get("filing_date", ""),
            case_type=header.get("case_type", ""),
            status=header.get("status", ""),
            court=header.get("court", self.config.court),
            parties=self.parse_parties(html),
            events=self.parse_events(html),
        )

    def scrape(self) -> Iterator[Case]:
        """Run the full crawl, yielding one :class:`Case` per case detail page.

        Honors the checkpoint (skips already-processed cases) and logs progress.
        Parsing failures on a single case are logged and skipped so one bad page
        doesn't abort a long crawl.
        """
        seen: set[str] = set()
        for page_url in self.search_page_urls():
            logger.info("fetching search page", extra={"url": page_url})
            try:
                results_html = self.fetcher.get(page_url)
            except Exception as exc:  # noqa: BLE001
                logger.error("search page failed", extra={"url": page_url, "error": str(exc)})
                continue

            for case_ref in self.parse_search_results(results_html):
                if case_ref in seen:
                    continue
                seen.add(case_ref)

                if self.checkpoint and self.checkpoint.is_done(case_ref):
                    logger.debug("skipping (checkpointed)", extra={"case_ref": case_ref})
                    continue

                case = self._scrape_one(case_ref)
                if case is not None:
                    yield case
                if self.checkpoint:
                    self.checkpoint.mark_done(case_ref)

    def _scrape_one(self, case_ref: str) -> Case | None:
        case_url = self.build_case_url(case_ref)
        try:
            case_html = self.fetcher.get(case_url)
        except FileNotFoundError:
            # Expected during offline demos: a candidate case number with no
            # fixture simply doesn't exist. Not an error.
            logger.debug("no case for reference", extra={"case_ref": case_ref})
            return None
        except Exception as exc:  # noqa: BLE001
            logger.error("case fetch failed", extra={"case_ref": case_ref, "error": str(exc)})
            return None

        try:
            case = self.parse_case(case_html, case_ref)
        except Exception as exc:  # noqa: BLE001
            logger.error("case parse failed", extra={"case_ref": case_ref, "error": str(exc)})
            return None

        logger.info(
            "parsed case",
            extra={
                "case_number": case.case_number,
                "parties": len(case.parties),
                "attorneys": len(case.attorneys()),
            },
        )
        return case

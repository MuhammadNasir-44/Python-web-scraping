"""Parser tests: run each adapter against the synthetic fixtures.

These assert the full parse (header + parties + attorneys + events) for both the
ASP.NET and JS-portal adapters, covering the 0 / 1 / 5-attorney and stacked-cell
edge cases.
"""

from __future__ import annotations

from court_scraper.base import BaseScraper
from court_scraper.models import Case
from court_scraper.parsing import split_name, split_stacked_cell


def _parse(scraper: BaseScraper, case_ref: str) -> Case:
    html = scraper.fetcher.get(scraper.build_case_url(case_ref))
    return scraper.parse_case(html, case_ref)


# --------------------------------------------------------------------------- #
# Unit tests for the shared name / cell helpers
# --------------------------------------------------------------------------- #
def test_split_name_last_first_with_suffix() -> None:
    a = split_name("Smith, John Q. Jr.")
    assert (a.first_name, a.middle_name, a.last_name, a.suffix) == ("John", "Q.", "Smith", "Jr.")


def test_split_name_first_last_with_roman_suffix() -> None:
    a = split_name("Daniel O'Sullivan III")
    assert (a.first_name, a.last_name, a.suffix) == ("Daniel", "O'Sullivan", "III")


def test_split_name_hyphenated_given_name() -> None:
    a = split_name("Kim, Soo-Jin")
    assert (a.first_name, a.last_name) == ("Soo-Jin", "Kim")


def test_split_stacked_cell_date_and_location() -> None:
    assert split_stacked_cell("04/02/2024\nCourtroom 3A") == ("04/02/2024", "Courtroom 3A")


def test_split_stacked_cell_date_only() -> None:
    assert split_stacked_cell("04/02/2024") == ("04/02/2024", "")


# --------------------------------------------------------------------------- #
# Travis (ASP.NET) adapter
# --------------------------------------------------------------------------- #
def test_travis_search_lists_all_cases(travis_scraper: BaseScraper) -> None:
    (page_url,) = list(travis_scraper.search_page_urls())
    refs = travis_scraper.parse_search_results(travis_scraper.fetcher.get(page_url))
    assert refs == [
        "D-1-GN-24-000001",
        "D-1-GN-24-000002",
        "D-1-GN-24-000003",
        "D-1-GN-24-000004",
    ]


def test_travis_one_attorney(travis_scraper: BaseScraper) -> None:
    case = _parse(travis_scraper, "D-1-GN-24-000001")
    assert case.county == "Travis County"
    assert case.case_number == "D-1-GN-24-000001"
    assert case.filing_date == "2024-03-14"
    assert case.status == "Open"
    pairs = case.attorneys()
    assert len(pairs) == 1
    party, attorney = pairs[0]
    assert party.role == "Plaintiff"
    assert (attorney.first_name, attorney.last_name, attorney.suffix) == ("John", "Smith", "Jr.")
    # Event stacks date + location in one cell.
    assert case.events[0].date == "2024-04-02"
    assert case.events[0].location == "Courtroom 3A"


def test_travis_zero_attorneys(travis_scraper: BaseScraper) -> None:
    case = _parse(travis_scraper, "D-1-GN-24-000002")
    assert case.attorneys() == []  # "Pro Se" and blank cell both yield none
    assert len(case.parties) == 2


def test_travis_five_attorneys(travis_scraper: BaseScraper) -> None:
    case = _parse(travis_scraper, "D-1-GN-24-000003")
    assert len(case.attorneys()) == 5
    last_names = {a.last_name for _, a in case.attorneys()}
    assert {"Nguyen", "O'Brien", "Garcia", "Washington", "Patel"} == last_names
    # Suffix correctly lifted from "Washington, Andre L. III".
    washington = next(a for _, a in case.attorneys() if a.last_name == "Washington")
    assert washington.suffix == "III"
    assert washington.middle_name == "L."


def test_travis_date_and_suffix_normalization(travis_scraper: BaseScraper) -> None:
    case = _parse(travis_scraper, "D-1-GN-24-000004")
    assert case.filing_date == "2024-01-09"  # "January 9, 2024" normalized
    fitz = next(a for _, a in case.attorneys() if a.last_name == "Fitzgerald")
    assert fitz.suffix == "Sr."
    assert case.events[0].location == "Mediation Center, Suite 400"


# --------------------------------------------------------------------------- #
# Harris (JS portal) adapter
# --------------------------------------------------------------------------- #
def test_harris_pagination_across_two_pages(harris_scraper: BaseScraper) -> None:
    urls = list(harris_scraper.search_page_urls())
    assert len(urls) == 2
    refs: list[str] = []
    for url in urls:
        refs.extend(harris_scraper.parse_search_results(harris_scraper.fetcher.get(url)))
    assert refs == [
        "2024-CV-01001A",
        "2024-CV-01002B",
        "2024-CV-01003C",
        "2024-PR-00500E",
    ]


def test_harris_one_attorney(harris_scraper: BaseScraper) -> None:
    case = _parse(harris_scraper, "2024-CV-01001A")
    assert case.filing_date == "2024-01-05"
    assert case.court == "County Civil Court at Law No. 2"
    assert len(case.attorneys()) == 1  # defendant is "Pro Se"
    _, attorney = case.attorneys()[0]
    assert (attorney.first_name, attorney.middle_name, attorney.last_name) == (
        "Rebecca",
        "Ann",
        "Lindqvist",
    )


def test_harris_zero_attorneys(harris_scraper: BaseScraper) -> None:
    case = _parse(harris_scraper, "2024-CV-01002B")
    assert case.attorneys() == []  # "Unrepresented" + empty <ul>


def test_harris_five_attorneys(harris_scraper: BaseScraper) -> None:
    case = _parse(harris_scraper, "2024-CV-01003C")
    assert len(case.attorneys()) == 5
    beaumont = next(a for _, a in case.attorneys() if a.last_name == "Beaumont")
    assert beaumont.suffix == "Jr."
    assert beaumont.first_name == "Charles"


def test_harris_stacked_event_cell(harris_scraper: BaseScraper) -> None:
    case = _parse(harris_scraper, "2024-PR-00500E")
    ev = case.events[0]
    assert ev.date == "2024-04-10"
    assert ev.location == "Probate Courtroom, 3rd Floor"
    assert len(case.attorneys()) == 1

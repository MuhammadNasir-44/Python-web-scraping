"""The pandas pipeline: explode → normalize → dedup → export.

Takes the normalized :class:`~court_scraper.models.Case` objects the scrapers
yield and flattens them to a tidy table with exactly one row per attorney, then
writes a 14-column CSV.

Output columns (order is contractual — downstream consumers depend on it)::

    County, Case Number, Case Name, Filing Date, Type, Status, Court,
    First Name, Middle Name, Last Name, Suffix, Party (Plaintiff/Defendant),
    Events / Hearings, Events / Hearings (cont.)

Attorney explosion rules
------------------------
* A case with N attorneys becomes N rows (all case-level fields repeated).
* A case with **zero** attorneys still produces one row (blank name fields) so
  the case is never silently dropped from the dataset.
* The ``Party (Plaintiff/Defendant)`` column carries the role of the party that
  the attorney represents.

Events columns
--------------
Each event renders as ``"<date> — <description> [<location>]"``. The **first**
event goes in ``Events / Hearings``; any remaining events are joined with
``"; "`` into ``Events / Hearings (cont.)``. This mirrors the common legacy
court-export convention of a primary hearing column plus a continuation column.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from court_scraper.models import Case, Event
from court_scraper.parsing import clean_text

COLUMNS: list[str] = [
    "County",
    "Case Number",
    "Case Name",
    "Filing Date",
    "Type",
    "Status",
    "Court",
    "First Name",
    "Middle Name",
    "Last Name",
    "Suffix",
    "Party (Plaintiff/Defendant)",
    "Events / Hearings",
    "Events / Hearings (cont.)",
]


def _format_event(event: Event) -> str:
    text = f"{event.date} — {event.description}".strip(" —")
    if event.location:
        text = f"{text} [{event.location}]"
    return clean_text(text)


def _split_events(events: list[Event]) -> tuple[str, str]:
    """Return (primary, continuation) strings for the two event columns."""
    rendered = [_format_event(e) for e in events if _format_event(e)]
    if not rendered:
        return "", ""
    primary = rendered[0]
    continuation = "; ".join(rendered[1:])
    return primary, continuation


class CasePipeline:
    """Flatten cases to a normalized attorney-level DataFrame and export CSV."""

    def __init__(self) -> None:
        self._rows: list[dict[str, str]] = []

    def add_case(self, case: Case) -> None:
        events_primary, events_cont = _split_events(case.events)
        base = {
            "County": clean_text(case.county),
            "Case Number": clean_text(case.case_number),
            "Case Name": clean_text(case.case_name),
            "Filing Date": clean_text(case.filing_date),
            "Type": clean_text(case.case_type),
            "Status": clean_text(case.status),
            "Court": clean_text(case.court),
            "Events / Hearings": events_primary,
            "Events / Hearings (cont.)": events_cont,
        }

        pairs = case.attorneys()
        if not pairs:
            # Preserve the case with blank attorney/party fields.
            self._rows.append(
                {
                    **base,
                    "First Name": "",
                    "Middle Name": "",
                    "Last Name": "",
                    "Suffix": "",
                    "Party (Plaintiff/Defendant)": "",
                }
            )
            return

        for party, attorney in pairs:
            self._rows.append(
                {
                    **base,
                    "First Name": clean_text(attorney.first_name),
                    "Middle Name": clean_text(attorney.middle_name),
                    "Last Name": clean_text(attorney.last_name),
                    "Suffix": clean_text(attorney.suffix),
                    "Party (Plaintiff/Defendant)": clean_text(party.role),
                }
            )

    def add_cases(self, cases: Iterable[Case]) -> None:
        for case in cases:
            self.add_case(case)

    def to_dataframe(self) -> pd.DataFrame:
        """Build the final DataFrame: correct columns, deduped, sorted."""
        df = pd.DataFrame(self._rows, columns=COLUMNS)
        if df.empty:
            return df

        # Consistency: every cell is a trimmed string (already cleaned on add,
        # but this guards against any NaN from column construction).
        df = df.fillna("").astype(str)

        # Dedup: collapse fully-identical rows that can arise when the same case
        # is reached via overlapping search pages or sequence ranges.
        df = df.drop_duplicates(ignore_index=True)

        # Stable, human-friendly ordering.
        df = df.sort_values(
            by=["County", "Case Number", "Last Name", "First Name"],
            kind="stable",
        ).reset_index(drop=True)
        return df

    def to_csv(self, path: str) -> pd.DataFrame:
        """Write the CSV and return the DataFrame that was written."""
        df = self.to_dataframe()
        df.to_csv(path, index=False)
        return df

    @property
    def row_count(self) -> int:
        return len(self._rows)

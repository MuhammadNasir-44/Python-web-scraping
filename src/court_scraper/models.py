"""Domain models for court case data.

These dataclasses are the internal, normalized representation that every county
adapter produces. Keeping the models decoupled from any specific site's HTML is
what lets a single pandas pipeline flatten output from all counties uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Attorney:
    """A single attorney of record, with the name split into components.

    County portals present names inconsistently ("Smith, John Q. Jr." vs.
    "John Quincy Smith"). Adapters are responsible for splitting into these
    fields; :func:`court_scraper.parsing.split_name` provides a default.
    """

    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    suffix: str = ""

    def is_empty(self) -> bool:
        return not any((self.first_name, self.middle_name, self.last_name, self.suffix))


@dataclass
class Party:
    """A party to the case (e.g. a Plaintiff or Defendant) and its attorneys."""

    name: str
    role: str  # "Plaintiff" or "Defendant"
    attorneys: list[Attorney] = field(default_factory=list)


@dataclass
class Event:
    """A docket event or hearing on the case."""

    date: str
    description: str
    location: str = ""


@dataclass
class Case:
    """A normalized civil court case, the unit every adapter yields."""

    county: str
    case_number: str
    case_name: str
    filing_date: str
    case_type: str
    status: str
    court: str
    parties: list[Party] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)

    def attorneys(self) -> list[tuple[Party, Attorney]]:
        """Flatten to (party, attorney) pairs across all parties."""
        pairs: list[tuple[Party, Attorney]] = []
        for party in self.parties:
            for attorney in party.attorneys:
                pairs.append((party, attorney))
        return pairs

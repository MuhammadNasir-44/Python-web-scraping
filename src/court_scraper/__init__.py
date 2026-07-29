"""Texas court records scraper.

A config-driven, adapter-based framework for extracting civil court case and
attorney data from county court portals, normalizing it, and exporting a flat
CSV (one row per attorney).

The package ships with a fully offline demo that runs the scrapers against
synthetic HTML fixtures — no live government sites are contacted.
"""

from __future__ import annotations

from court_scraper.base import BaseScraper
from court_scraper.case_numbers import CaseNumberGenerator
from court_scraper.models import Attorney, Case, Event, Party
from court_scraper.pipeline import CasePipeline

__version__ = "0.1.0"

__all__ = [
    "BaseScraper",
    "CaseNumberGenerator",
    "CasePipeline",
    "Attorney",
    "Case",
    "Event",
    "Party",
    "__version__",
]

"""Adapter registry.

Adapters register themselves under a string key (matching the ``adapter:`` field
in a county YAML config). :func:`get_adapter` resolves that key to a class so the
CLI can instantiate the right scraper purely from config.
"""

from __future__ import annotations

from court_scraper.adapters.harris import HarrisJsPortalScraper
from court_scraper.adapters.travis import TravisPublicAccessScraper
from court_scraper.base import BaseScraper

_REGISTRY: dict[str, type[BaseScraper]] = {
    "aspnet_public_access": TravisPublicAccessScraper,
    "js_portal": HarrisJsPortalScraper,
}


def get_adapter(key: str) -> type[BaseScraper]:
    try:
        return _REGISTRY[key]
    except KeyError:
        raise KeyError(
            f"unknown adapter {key!r}; registered adapters: {sorted(_REGISTRY)}"
        ) from None


def register_adapter(key: str, cls: type[BaseScraper]) -> None:
    """Register a new adapter class (used by third-party county plugins)."""
    _REGISTRY[key] = cls


__all__ = [
    "BaseScraper",
    "TravisPublicAccessScraper",
    "HarrisJsPortalScraper",
    "get_adapter",
    "register_adapter",
]

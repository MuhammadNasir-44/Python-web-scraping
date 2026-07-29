"""Shared pytest fixtures and path helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from court_scraper.adapters import get_adapter
from court_scraper.config import CountyConfig, load_county_config
from court_scraper.http_client import FixtureFetcher

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
FIXTURES_DIR = PROJECT_ROOT / "fixtures"


@pytest.fixture
def travis_config() -> CountyConfig:
    return load_county_config(CONFIG_DIR / "travis_county.yaml")


@pytest.fixture
def harris_config() -> CountyConfig:
    return load_county_config(CONFIG_DIR / "harris_county.yaml")


def build_scraper(config: CountyConfig):
    """Instantiate the configured adapter wired to the offline FixtureFetcher."""
    fetcher = FixtureFetcher(FIXTURES_DIR / config.key)
    adapter_cls = get_adapter(config.adapter)
    return adapter_cls(config, fetcher)


@pytest.fixture
def travis_scraper(travis_config: CountyConfig):
    return build_scraper(travis_config)


@pytest.fixture
def harris_scraper(harris_config: CountyConfig):
    return build_scraper(harris_config)

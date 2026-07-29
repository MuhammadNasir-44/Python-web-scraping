"""End-to-end: run both adapters against fixtures through the full pipeline.

This is the offline demo, asserted. It exercises search → paginate → open case →
parse → explode → export for both counties and checks the final CSV shape.
"""

from __future__ import annotations

from court_scraper.base import BaseScraper
from court_scraper.checkpoint import Checkpoint
from court_scraper.pipeline import COLUMNS, CasePipeline


def _run(scraper: BaseScraper, pipeline: CasePipeline) -> int:
    count = 0
    for case in scraper.scrape():
        pipeline.add_case(case)
        count += 1
    return count


def test_full_offline_run_both_counties(travis_scraper, harris_scraper, tmp_path) -> None:
    pipeline = CasePipeline()
    travis_cases = _run(travis_scraper, pipeline)
    harris_cases = _run(harris_scraper, pipeline)

    assert travis_cases == 4
    assert harris_cases == 4

    out = tmp_path / "cases.csv"
    df = pipeline.to_csv(str(out))

    assert list(df.columns) == COLUMNS
    assert out.exists()

    # Total attorney rows: Travis (1+0+5+2) + Harris (1+0+5+1), with the two
    # zero-attorney cases each contributing one blank-attorney row.
    #   Travis: 1 + 1(blank) + 5 + 2 = 9
    #   Harris: 1 + 1(blank) + 5 + 1 = 8
    assert len(df) == 17

    # Both counties present.
    assert set(df["County"]) == {"Travis County", "Harris County"}

    # Every filing date normalized to ISO (YYYY-MM-DD) or blank.
    for value in df["Filing Date"]:
        assert value == "" or (len(value) == 10 and value[4] == "-" and value[7] == "-")


def test_checkpoint_resume_skips_completed_cases(travis_config, tmp_path) -> None:
    from pathlib import Path

    from court_scraper.adapters import get_adapter
    from court_scraper.http_client import FixtureFetcher

    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures"
    cp_path = tmp_path / "travis.jsonl"
    fetcher = FixtureFetcher(fixtures_dir / travis_config.key)
    adapter_cls = get_adapter(travis_config.adapter)

    # First run: process everything, recording progress to the checkpoint.
    scraper1 = adapter_cls(travis_config, fetcher, checkpoint=Checkpoint(cp_path))
    first = list(scraper1.scrape())
    assert len(first) == 4

    # Second run with the same checkpoint: all cases already done → nothing new.
    scraper2 = adapter_cls(travis_config, fetcher, checkpoint=Checkpoint(cp_path))
    second = list(scraper2.scrape())
    assert second == []

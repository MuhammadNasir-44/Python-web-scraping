"""Command-line entry point.

Examples
--------
Run every configured county against the bundled fixtures and write a CSV::

    court-scraper --config-dir config --fixtures --out output/cases.csv

Run a single county live (rate limited, retried) — requires network + a real
portal, and is intentionally not exercised by the offline demo::

    court-scraper --config config/travis_county.yaml --live --out out.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from court_scraper.adapters import get_adapter
from court_scraper.case_numbers import CaseNumberGenerator
from court_scraper.checkpoint import Checkpoint
from court_scraper.config import CountyConfig, load_all_configs, load_county_config
from court_scraper.http_client import FixtureFetcher, Fetcher, HttpFetcher
from court_scraper.logging_config import configure_logging, get_logger
from court_scraper.pipeline import CasePipeline

logger = get_logger(__name__)


def _build_fetcher(cfg: CountyConfig, use_fixtures: bool, project_root: Path) -> Fetcher:
    if use_fixtures:
        fixtures_dir = cfg.fixtures_dir or f"fixtures/{cfg.key}"
        return FixtureFetcher(project_root / fixtures_dir)
    return HttpFetcher(
        rate_per_sec=cfg.rate_limit_per_sec,
        max_retries=cfg.max_retries,
    )


def _run_county(
    cfg: CountyConfig,
    pipeline: CasePipeline,
    use_fixtures: bool,
    project_root: Path,
    checkpoint_dir: Path | None,
) -> int:
    fetcher = _build_fetcher(cfg, use_fixtures, project_root)
    checkpoint = None
    if checkpoint_dir is not None:
        checkpoint = Checkpoint(checkpoint_dir / f"{cfg.key}.jsonl")

    adapter_cls = get_adapter(cfg.adapter)
    scraper = adapter_cls(cfg, fetcher, checkpoint=checkpoint)

    count = 0
    for case in scraper.scrape():
        pipeline.add_case(case)
        count += 1
    logger.info("county complete", extra={"county": cfg.county, "cases": count})
    return count


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="court-scraper", description=__doc__)
    src = p.add_mutually_exclusive_group()
    src.add_argument("--config", help="Path to a single county YAML config.")
    src.add_argument(
        "--config-dir",
        help="Directory of county YAML configs (all *.yaml are run).",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--fixtures",
        action="store_true",
        help="Run offline against local HTML fixtures (default).",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="Fetch from live portals (rate limited). Not used by the demo.",
    )
    p.add_argument("--out", default="output/cases.csv", help="Output CSV path.")
    p.add_argument(
        "--checkpoint-dir",
        default="checkpoints",
        help="Directory for resume checkpoints ('none' to disable).",
    )
    p.add_argument(
        "--list-case-numbers",
        action="store_true",
        help="Print the case numbers each config's sequences would enumerate, then exit.",
    )
    p.add_argument("--log-level", default="INFO")
    p.add_argument(
        "--log-plain",
        action="store_true",
        help="Human-readable logs instead of JSON.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(level=args.log_level, json_output=not args.log_plain)

    project_root = Path.cwd()
    use_fixtures = not args.live  # fixtures are the default

    if args.config:
        configs = [load_county_config(args.config)]
    else:
        config_dir = args.config_dir or "config"
        configs = load_all_configs(config_dir)

    if not configs:
        logger.error("no county configs found")
        return 2

    if args.list_case_numbers:
        for cfg in configs:
            gen = CaseNumberGenerator.from_config(cfg.sequences)
            numbers = gen.generate()
            print(f"# {cfg.county}: {len(numbers)} candidate case numbers")
            for number in numbers:
                print(number)
        return 0

    checkpoint_dir: Path | None
    if args.checkpoint_dir.lower() == "none":
        checkpoint_dir = None
    else:
        checkpoint_dir = Path(args.checkpoint_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

    pipeline = CasePipeline()
    total = 0
    for cfg in configs:
        total += _run_county(cfg, pipeline, use_fixtures, project_root, checkpoint_dir)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pipeline.to_csv(str(out_path))

    logger.info(
        "done",
        extra={"cases": total, "rows": len(df), "out": str(out_path)},
    )
    print(f"Wrote {len(df)} attorney rows from {total} cases to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

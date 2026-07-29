"""Config loading. Each county is described by one YAML file.

The config drives everything site-specific — base URL, CSS selectors, and the
case-number sequences — so adding a county is (mostly) a data exercise rather
than a code one. See ``config/*.yaml`` for annotated examples.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CountyConfig:
    """Parsed representation of a county YAML file."""

    key: str  # short identifier, e.g. "travis"
    county: str  # display name, e.g. "Travis County"
    adapter: str  # adapter class registry key, e.g. "aspnet_public_access"
    base_url: str
    court: str
    selectors: dict[str, Any]
    sequences: list[dict[str, Any]]
    fixtures_dir: str | None = None
    rate_limit_per_sec: float = 1.0
    max_retries: int = 3
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CountyConfig":
        known = {
            "key",
            "county",
            "adapter",
            "base_url",
            "court",
            "selectors",
            "sequences",
            "fixtures_dir",
            "rate_limit_per_sec",
            "max_retries",
        }
        missing = {"key", "county", "adapter", "base_url", "selectors", "sequences"} - data.keys()
        if missing:
            raise ValueError(f"county config missing required keys: {sorted(missing)}")
        return cls(
            key=data["key"],
            county=data["county"],
            adapter=data["adapter"],
            base_url=data["base_url"],
            court=data.get("court", ""),
            selectors=data["selectors"],
            sequences=data["sequences"],
            fixtures_dir=data.get("fixtures_dir"),
            rate_limit_per_sec=float(data.get("rate_limit_per_sec", 1.0)),
            max_retries=int(data.get("max_retries", 3)),
            extra={k: v for k, v in data.items() if k not in known},
        )


def load_county_config(path: str | Path) -> CountyConfig:
    """Load and validate a single county YAML file."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping at the top level")
    return CountyConfig.from_dict(data)


def load_all_configs(config_dir: str | Path) -> list[CountyConfig]:
    """Load every ``*.yaml`` file in a directory."""
    config_dir = Path(config_dir)
    configs = [load_county_config(p) for p in sorted(config_dir.glob("*.yaml"))]
    return configs

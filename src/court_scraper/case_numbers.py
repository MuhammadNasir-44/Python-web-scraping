"""Case-number sequence generation.

Texas civil case numbers follow county-specific conventions. This module models
three sequence patterns that repeatedly show up across county portals and lets a
crawl enumerate candidate case numbers to look up:

1. ``plain``          — a single numeric range dropped into a template.
2. ``letter_suffix``  — a numeric range crossed with a set of letter suffixes
                        (A-H), where *every* number gets *every* suffix
                        (a cartesian product).
3. ``per_suffix``     — like ``letter_suffix`` but each suffix carries its own,
                        independent numeric range.

Each pattern is driven by a ``template`` string with two named fields:

    ``{seq}``     the (zero-padded) sequence number
    ``{suffix}``  the letter suffix (empty string for the ``plain`` pattern)

Example template: ``"D-1-GN-{year}-{seq}{suffix}"`` where ``{year}`` is supplied
as a constant in ``extra`` (see :meth:`SequenceSpec.from_config`).
"""

from __future__ import annotations

import string
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

# The A-H suffix alphabet used by the per-court sub-docket convention modeled
# here. Exposed as a module constant so tests and configs can reference it.
DEFAULT_SUFFIXES: tuple[str, ...] = tuple(string.ascii_uppercase[:8])  # A..H


@dataclass(frozen=True)
class SequenceSpec:
    """A declarative description of one case-number sequence.

    Attributes:
        pattern: One of ``"plain"``, ``"letter_suffix"``, ``"per_suffix"``.
        template: Format string using ``{seq}`` and ``{suffix}`` (plus any
            constants provided in ``extra``).
        start: First sequence number (inclusive). Used by ``plain`` and
            ``letter_suffix``.
        end: Last sequence number (inclusive). Used by ``plain`` and
            ``letter_suffix``.
        width: Zero-pad width for ``{seq}``.
        suffixes: Ordered suffix alphabet for the suffix-bearing patterns.
        per_suffix_ranges: For ``per_suffix``, maps each suffix to an
            ``(start, end)`` inclusive range.
        extra: Constant fields merged into the template (e.g. ``{"year": "24"}``).
    """

    pattern: str
    template: str
    start: int = 1
    end: int = 1
    width: int = 6
    suffixes: tuple[str, ...] = DEFAULT_SUFFIXES
    per_suffix_ranges: dict[str, tuple[int, int]] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    _VALID_PATTERNS = ("plain", "letter_suffix", "per_suffix")

    def __post_init__(self) -> None:
        if self.pattern not in self._VALID_PATTERNS:
            raise ValueError(
                f"unknown pattern {self.pattern!r}; expected one of {self._VALID_PATTERNS}"
            )
        if self.pattern in ("plain", "letter_suffix"):
            if self.start > self.end:
                raise ValueError(f"start ({self.start}) must be <= end ({self.end})")
        if self.pattern == "per_suffix":
            if not self.per_suffix_ranges:
                raise ValueError("per_suffix pattern requires 'per_suffix_ranges'")
            for suffix, (lo, hi) in self.per_suffix_ranges.items():
                if lo > hi:
                    raise ValueError(
                        f"per_suffix_ranges[{suffix!r}] start ({lo}) must be <= end ({hi})"
                    )

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "SequenceSpec":
        """Build a spec from a plain dict (as loaded from YAML)."""
        raw_ranges = cfg.get("per_suffix_ranges") or {}
        per_suffix_ranges = {
            str(k): (int(v["start"]), int(v["end"])) for k, v in raw_ranges.items()
        }
        suffixes = cfg.get("suffixes")
        return cls(
            pattern=cfg["pattern"],
            template=cfg["template"],
            start=int(cfg.get("start", 1)),
            end=int(cfg.get("end", 1)),
            width=int(cfg.get("width", 6)),
            suffixes=tuple(suffixes) if suffixes else DEFAULT_SUFFIXES,
            per_suffix_ranges=per_suffix_ranges,
            extra=dict(cfg.get("extra", {})),
        )

    def _format(self, seq: int, suffix: str) -> str:
        return self.template.format(
            seq=str(seq).zfill(self.width),
            suffix=suffix,
            **self.extra,
        )


class CaseNumberGenerator:
    """Enumerate candidate case numbers from one or more :class:`SequenceSpec`.

    The generator is a pure, deterministic iterator: given the same specs it
    always yields the same numbers in the same order, which makes crawls
    reproducible and lets the checkpoint/resume machinery skip a prefix.
    """

    def __init__(self, specs: list[SequenceSpec]):
        if not specs:
            raise ValueError("CaseNumberGenerator requires at least one SequenceSpec")
        self._specs = specs

    @classmethod
    def from_config(cls, sequences: list[dict[str, Any]]) -> "CaseNumberGenerator":
        return cls([SequenceSpec.from_config(cfg) for cfg in sequences])

    def _iter_spec(self, spec: SequenceSpec) -> Iterator[str]:
        if spec.pattern == "plain":
            for seq in range(spec.start, spec.end + 1):
                yield spec._format(seq, "")

        elif spec.pattern == "letter_suffix":
            # Every number crossed with every suffix (cartesian product).
            # Grouped by number so related sub-dockets are yielded together.
            for seq in range(spec.start, spec.end + 1):
                for suffix in spec.suffixes:
                    yield spec._format(seq, suffix)

        elif spec.pattern == "per_suffix":
            # Each suffix has an independent numeric range.
            for suffix in spec.suffixes:
                if suffix not in spec.per_suffix_ranges:
                    continue
                lo, hi = spec.per_suffix_ranges[suffix]
                for seq in range(lo, hi + 1):
                    yield spec._format(seq, suffix)

    def __iter__(self) -> Iterator[str]:
        seen: set[str] = set()
        for spec in self._specs:
            for number in self._iter_spec(spec):
                # De-duplicate across specs so overlapping ranges don't produce
                # the same candidate twice.
                if number not in seen:
                    seen.add(number)
                    yield number

    def generate(self) -> list[str]:
        """Materialize all candidate case numbers as a list."""
        return list(self)

    def count(self) -> int:
        """Number of unique candidates that :meth:`__iter__` will yield."""
        return sum(1 for _ in self)

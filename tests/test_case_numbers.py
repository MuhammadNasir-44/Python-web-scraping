"""Tests for the CaseNumberGenerator — the sequence-pattern highlight."""

from __future__ import annotations

import pytest

from court_scraper.case_numbers import (
    DEFAULT_SUFFIXES,
    CaseNumberGenerator,
    SequenceSpec,
)


def test_plain_range_is_zero_padded_and_inclusive() -> None:
    spec = SequenceSpec(
        pattern="plain",
        template="D-1-GN-{year}-{seq}{suffix}",
        start=1,
        end=3,
        width=6,
        extra={"year": "24"},
    )
    got = CaseNumberGenerator([spec]).generate()
    assert got == [
        "D-1-GN-24-000001",
        "D-1-GN-24-000002",
        "D-1-GN-24-000003",
    ]


def test_letter_suffix_is_cartesian_product_grouped_by_number() -> None:
    spec = SequenceSpec(
        pattern="letter_suffix",
        template="2024-CV-{seq}{suffix}",
        start=1001,
        end=1002,
        width=5,
        suffixes=("A", "B"),
    )
    got = CaseNumberGenerator([spec]).generate()
    # Every number crossed with every suffix, grouped by number.
    assert got == [
        "2024-CV-01001A",
        "2024-CV-01001B",
        "2024-CV-01002A",
        "2024-CV-01002B",
    ]


def test_per_suffix_uses_independent_ranges() -> None:
    spec = SequenceSpec(
        pattern="per_suffix",
        template="2024-PR-{seq}{suffix}",
        width=5,
        suffixes=("E", "F"),
        per_suffix_ranges={"E": (500, 501), "F": (700, 700)},
    )
    got = CaseNumberGenerator([spec]).generate()
    assert got == [
        "2024-PR-00500E",
        "2024-PR-00501E",
        "2024-PR-00700F",
    ]


def test_per_suffix_skips_suffixes_without_a_range() -> None:
    spec = SequenceSpec(
        pattern="per_suffix",
        template="{seq}{suffix}",
        width=3,
        suffixes=("E", "F", "G"),
        per_suffix_ranges={"F": (1, 2)},  # only F has a range
    )
    assert CaseNumberGenerator([spec]).generate() == ["001F", "002F"]


def test_default_suffix_alphabet_is_a_through_h() -> None:
    assert DEFAULT_SUFFIXES == ("A", "B", "C", "D", "E", "F", "G", "H")


def test_generator_dedups_across_overlapping_specs() -> None:
    a = SequenceSpec(pattern="plain", template="{seq}{suffix}", start=1, end=3, width=1)
    b = SequenceSpec(pattern="plain", template="{seq}{suffix}", start=2, end=4, width=1)
    got = CaseNumberGenerator([a, b]).generate()
    assert got == ["1", "2", "3", "4"]  # no duplicate "2" / "3"


def test_count_matches_generate_length() -> None:
    spec = SequenceSpec(
        pattern="letter_suffix",
        template="{seq}{suffix}",
        start=1,
        end=10,
        width=2,
        suffixes=("A", "B", "C"),
    )
    gen = CaseNumberGenerator([spec])
    assert gen.count() == len(gen.generate()) == 30


def test_from_config_round_trips_per_suffix() -> None:
    gen = CaseNumberGenerator.from_config(
        [
            {
                "pattern": "per_suffix",
                "template": "2024-PR-{seq}{suffix}",
                "width": 5,
                "suffixes": ["E", "H"],
                "per_suffix_ranges": {
                    "E": {"start": 500, "end": 500},
                    "H": {"start": 950, "end": 951},
                },
            }
        ]
    )
    assert gen.generate() == ["2024-PR-00500E", "2024-PR-00950H", "2024-PR-00951H"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"pattern": "nope", "template": "{seq}"},
        {"pattern": "plain", "template": "{seq}", "start": 5, "end": 1},
        {"pattern": "per_suffix", "template": "{seq}"},  # no ranges
    ],
)
def test_invalid_specs_raise(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        SequenceSpec(**kwargs)


def test_empty_generator_raises() -> None:
    with pytest.raises(ValueError):
        CaseNumberGenerator([])

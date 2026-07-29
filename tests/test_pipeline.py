"""Tests for the pandas pipeline: attorney explosion, columns, dedup, export."""

from __future__ import annotations

from court_scraper.models import Attorney, Case, Event, Party
from court_scraper.pipeline import COLUMNS, CasePipeline


def _case(**overrides) -> Case:
    base = dict(
        county="Travis County",
        case_number="D-1-GN-24-000001",
        case_name="Doe vs. Acme",
        filing_date="2024-03-14",
        case_type="Contract",
        status="Open",
        court="201st District Court",
    )
    base.update(overrides)
    return Case(**base)


def test_columns_are_exactly_the_14_contract_columns() -> None:
    pipe = CasePipeline()
    pipe.add_case(_case())
    df = pipe.to_dataframe()
    assert list(df.columns) == COLUMNS
    assert len(COLUMNS) == 14


def test_case_explodes_to_one_row_per_attorney() -> None:
    case = _case(
        parties=[
            Party(
                name="Jane Doe",
                role="Plaintiff",
                attorneys=[
                    Attorney(first_name="John", last_name="Smith"),
                    Attorney(first_name="Amy", last_name="Lee"),
                ],
            ),
            Party(
                name="Acme",
                role="Defendant",
                attorneys=[Attorney(first_name="Maria", last_name="Garcia")],
            ),
        ]
    )
    pipe = CasePipeline()
    pipe.add_case(case)
    df = pipe.to_dataframe()
    assert len(df) == 3
    # Case-level fields are repeated on every row.
    assert set(df["Case Number"]) == {"D-1-GN-24-000001"}
    assert sorted(df["Last Name"]) == ["Garcia", "Lee", "Smith"]
    # Party role travels with the attorney.
    smith = df[df["Last Name"] == "Smith"].iloc[0]
    assert smith["Party (Plaintiff/Defendant)"] == "Plaintiff"
    garcia = df[df["Last Name"] == "Garcia"].iloc[0]
    assert garcia["Party (Plaintiff/Defendant)"] == "Defendant"


def test_zero_attorney_case_still_produces_one_row() -> None:
    case = _case(parties=[Party(name="Estate", role="Plaintiff", attorneys=[])])
    pipe = CasePipeline()
    pipe.add_case(case)
    df = pipe.to_dataframe()
    assert len(df) == 1
    row = df.iloc[0]
    assert row["First Name"] == ""
    assert row["Last Name"] == ""
    assert row["Party (Plaintiff/Defendant)"] == ""
    assert row["Case Number"] == "D-1-GN-24-000001"  # case not dropped


def test_events_split_primary_and_continuation() -> None:
    case = _case(
        parties=[Party(name="X", role="Plaintiff", attorneys=[Attorney(last_name="Smith")])],
        events=[
            Event(date="2024-04-02", description="Initial Hearing", location="Courtroom 3A"),
            Event(date="2024-07-18", description="Docket Call"),
            Event(date="2024-09-30", description="Trial"),
        ],
    )
    pipe = CasePipeline()
    pipe.add_case(case)
    row = pipe.to_dataframe().iloc[0]
    assert row["Events / Hearings"] == "2024-04-02 — Initial Hearing [Courtroom 3A]"
    assert row["Events / Hearings (cont.)"] == "2024-07-18 — Docket Call; 2024-09-30 — Trial"


def test_no_events_leaves_both_event_columns_blank() -> None:
    case = _case(
        parties=[Party(name="X", role="Plaintiff", attorneys=[Attorney(last_name="Smith")])],
        events=[],
    )
    pipe = CasePipeline()
    pipe.add_case(case)
    r = pipe.to_dataframe().iloc[0]
    assert r["Events / Hearings"] == ""
    assert r["Events / Hearings (cont.)"] == ""


def test_duplicate_rows_are_collapsed() -> None:
    case = _case(
        parties=[Party(name="X", role="Plaintiff", attorneys=[Attorney(last_name="Smith")])]
    )
    pipe = CasePipeline()
    pipe.add_case(case)
    pipe.add_case(case)  # same case scraped twice (overlapping ranges)
    df = pipe.to_dataframe()
    assert len(df) == 1


def test_to_csv_writes_all_columns(tmp_path) -> None:
    case = _case(
        parties=[Party(name="X", role="Plaintiff", attorneys=[Attorney(last_name="Smith")])]
    )
    pipe = CasePipeline()
    pipe.add_case(case)
    out = tmp_path / "cases.csv"
    pipe.to_csv(str(out))
    text = out.read_text(encoding="utf-8")
    header = text.splitlines()[0]
    assert header == ",".join(COLUMNS)

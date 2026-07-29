"""Shared parsing / normalization helpers used by the pipeline and adapters."""

from __future__ import annotations

import re
from datetime import datetime

from court_scraper.models import Attorney

# Suffixes we recognize and lift out of a name string.
_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v", "esq"}

# Placeholder tokens portals use where an attorney would go but none exists.
# These must never be parsed into an Attorney.
_NON_ATTORNEY_MARKERS = {
    "",
    "pro se",
    "prose",
    "pro-se",
    "pro per",
    "n/a",
    "na",
    "none",
    "unrepresented",
    "not represented",
    "no attorney",
}


def is_non_attorney(value: str | None) -> bool:
    """True if ``value`` is a placeholder meaning "no attorney of record"."""
    return clean_text(value).replace(".", "").lower() in _NON_ATTORNEY_MARKERS

# Date formats we try, in order, when normalizing to ISO (YYYY-MM-DD).
_DATE_FORMATS = (
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%m/%d/%y",
    "%Y-%m-%d",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %b %Y",
)


def clean_text(value: str | None) -> str:
    """Collapse internal whitespace and strip. ``None`` becomes ``""``."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def normalize_date(value: str | None) -> str:
    """Normalize a messy date string to ISO ``YYYY-MM-DD``.

    Returns the cleaned-but-unparsed string if no known format matches, so we
    never silently drop data we couldn't interpret.
    """
    text = clean_text(value)
    if not text:
        return ""
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text


def _norm_suffix(token: str) -> str:
    """Return a canonical suffix (``Jr.``, ``III``) or ``""`` if not a suffix."""
    key = token.replace(".", "").lower()
    if key not in _NAME_SUFFIXES:
        return ""
    if key in {"ii", "iii", "iv", "v"}:
        return key.upper()
    return key.capitalize() + "."


def split_name(raw: str) -> Attorney:
    """Split a name string into first / middle / last / suffix.

    Handles both ``"Last, First Middle Suffix"`` and ``"First Middle Last"``
    orderings, which is the common variation between portals.
    """
    text = clean_text(raw)
    if not text:
        return Attorney()

    suffix = ""
    if "," in text:
        # "Last, First Middle [Suffix]" — but the suffix may follow a second comma
        # ("Smith, John Q., Jr.") or be trailing on the given-name part.
        last_part, _, rest = text.partition(",")
        rest = rest.strip()
        # A trailing ", Jr" style suffix.
        if "," in rest:
            given_part, _, tail = rest.rpartition(",")
            maybe = _norm_suffix(tail.strip())
            if maybe:
                suffix = maybe
                rest = given_part.strip()
        given_tokens = rest.split()
        last = last_part.strip()
    else:
        tokens = text.split()
        # Trailing suffix on a "First Middle Last Suffix" string.
        if len(tokens) >= 2 and _norm_suffix(tokens[-1]):
            suffix = _norm_suffix(tokens[-1])
            tokens = tokens[:-1]
        last = tokens[-1] if tokens else ""
        given_tokens = tokens[:-1]

    # A suffix may still be the last given token ("John Q Jr").
    if given_tokens and not suffix:
        maybe = _norm_suffix(given_tokens[-1])
        if maybe:
            suffix = maybe
            given_tokens = given_tokens[:-1]

    first = given_tokens[0] if given_tokens else ""
    middle = " ".join(given_tokens[1:]) if len(given_tokens) > 1 else ""
    return Attorney(
        first_name=first,
        middle_name=middle,
        last_name=last,
        suffix=suffix,
    )


def split_stacked_cell(value: str) -> tuple[str, str]:
    """Split a "stacked" cell that packs a date and a location together.

    County grids sometimes render an event's date on the first line and its
    location on the second inside a single ``<td>`` (separated by ``<br>`` which
    the HTML-to-text step turns into a newline). Returns ``(date, location)``.
    """
    parts = [clean_text(p) for p in re.split(r"[\r\n]+", value) if clean_text(p)]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])

"""Checkpoint / resume support.

A long crawl records which case numbers it has already processed to a JSON-lines
file. On restart the scraper loads the checkpoint and skips completed numbers,
so an interrupted multi-hour crawl continues instead of starting over.
"""

from __future__ import annotations

import json
from pathlib import Path


class Checkpoint:
    """Tracks processed case numbers for one (county) crawl.

    The backing file is append-only JSON-lines: one ``{"n": "<case number>"}``
    record per processed number. Appending (rather than rewriting) means a crash
    mid-write loses at most the last line, never the whole checkpoint.
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._done: set[str] = set()
        if self._path.exists():
            self._load()

    def _load(self) -> None:
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    self._done.add(json.loads(line)["n"])
                except (json.JSONDecodeError, KeyError):
                    continue  # tolerate a torn final line

    def is_done(self, case_number: str) -> bool:
        return case_number in self._done

    def mark_done(self, case_number: str) -> None:
        if case_number in self._done:
            return
        self._done.add(case_number)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"n": case_number}) + "\n")

    @property
    def completed_count(self) -> int:
        return len(self._done)

    def reset(self) -> None:
        """Forget all progress and delete the backing file."""
        self._done.clear()
        if self._path.exists():
            self._path.unlink()

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Protocol
from zipfile import ZipFile


@dataclass(frozen=True, slots=True)
class AdapterProbe:
    adapter_name: str
    compatible: bool
    archive_files: int
    source_files: int
    recognized_books: tuple[str, ...]
    unrecognized_book_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceRecord:
    source_file: str
    book_code: str
    chapter: int
    verse_label: str
    source_sequence: int
    raw_payload: str

    @property
    def source_locator(self) -> str:
        return f"{self.book_code} {self.chapter}:{self.verse_label}"


class SourceAdapter(Protocol):
    name: str

    def probe(self, archive: ZipFile) -> AdapterProbe:
        """Check whether an archive is compatible without mutating it."""

    def iter_records(self, archive: ZipFile) -> Iterator[SourceRecord]:
        """Stream source-shaped records in deterministic source order."""

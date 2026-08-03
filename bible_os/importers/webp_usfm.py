from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from zipfile import ZipFile, ZipInfo

from .base import AdapterProbe, SourceRecord

BOOK_ORDER = (
    "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT", "1SA", "2SA",
    "1KI", "2KI", "1CH", "2CH", "EZR", "NEH", "EST", "JOB", "PSA", "PRO",
    "ECC", "SNG", "ISA", "JER", "LAM", "EZK", "DAN", "HOS", "JOL", "AMO",
    "OBA", "JON", "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL", "MAT",
    "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL", "EPH", "PHP",
    "COL", "1TH", "2TH", "1TI", "2TI", "TIT", "PHM", "HEB", "JAS", "1PE",
    "2PE", "1JN", "2JN", "3JN", "JUD", "REV",
)
BOOK_INDEX = {book: index for index, book in enumerate(BOOK_ORDER)}

ID_RE = re.compile(r"^\\id\s+(?P<book>[A-Z0-9]{3})\b")
CHAPTER_RE = re.compile(r"^\\c\s+(?P<chapter>[0-9]+)\b")
VERSE_RE = re.compile(
    r"^\\v\s+(?P<label>[0-9]+(?:[-–][0-9]+)?[a-z]?)"
    r"(?:\s+(?P<payload>.*))?$"
)


@dataclass(frozen=True, slots=True)
class _Document:
    member: ZipInfo
    book_code: str
    text: str


class WebpUsfmAdapter:
    """Stream WEBP USFM verse records without normalizing source payloads."""

    name = "webp-usfm-v1"

    @staticmethod
    def _source_members(archive: ZipFile) -> list[ZipInfo]:
        return sorted(
            (
                member
                for member in archive.infolist()
                if not member.is_dir()
                and Path(member.filename).suffix.lower() in {".usfm", ".sfm"}
            ),
            key=lambda member: member.filename,
        )

    def _load_documents(self, archive: ZipFile) -> list[_Document]:
        documents: list[_Document] = []
        seen_ids: set[str] = set()

        for member in self._source_members(archive):
            text = archive.read(member).decode("utf-8-sig")
            book_code = ""
            for line in text.splitlines():
                match = ID_RE.match(line.strip())
                if match:
                    book_code = match.group("book")
                    break
            if not book_code:
                raise ValueError(f"USFM file has no \\id marker: {member.filename}")
            if book_code in seen_ids:
                raise ValueError(f"duplicate USFM book id: {book_code}")
            seen_ids.add(book_code)
            documents.append(_Document(member=member, book_code=book_code, text=text))

        return sorted(
            documents,
            key=lambda document: (
                BOOK_INDEX.get(document.book_code, len(BOOK_ORDER)),
                document.book_code,
                document.member.filename,
            ),
        )

    def probe(self, archive: ZipFile) -> AdapterProbe:
        documents = self._load_documents(archive)
        recognized = tuple(
            document.book_code
            for document in documents
            if document.book_code in BOOK_INDEX
        )
        unrecognized = tuple(
            document.book_code
            for document in documents
            if document.book_code not in BOOK_INDEX
        )
        return AdapterProbe(
            adapter_name=self.name,
            compatible=bool(recognized),
            archive_files=sum(not member.is_dir() for member in archive.infolist()),
            source_files=len(documents),
            recognized_books=recognized,
            unrecognized_book_ids=unrecognized,
        )

    def iter_records(self, archive: ZipFile) -> Iterator[SourceRecord]:
        sequence = 0
        for document in self._load_documents(archive):
            if document.book_code not in BOOK_INDEX:
                continue

            chapter: int | None = None
            previous_chapter = 0
            current_label: str | None = None
            current_payload: list[str] = []
            seen_loci: set[tuple[int, str]] = set()

            def flush() -> SourceRecord | None:
                nonlocal sequence, current_label, current_payload
                if current_label is None or chapter is None:
                    return None
                sequence += 1
                record = SourceRecord(
                    source_file=document.member.filename,
                    book_code=document.book_code,
                    chapter=chapter,
                    verse_label=current_label,
                    source_sequence=sequence,
                    raw_payload="\n".join(current_payload),
                )
                current_label = None
                current_payload = []
                return record

            for raw_line in document.text.splitlines():
                line = raw_line.rstrip("\r\n")
                stripped = line.strip()

                chapter_match = CHAPTER_RE.match(stripped)
                if chapter_match:
                    pending = flush()
                    if pending is not None:
                        yield pending
                    next_chapter = int(chapter_match.group("chapter"))
                    if next_chapter <= 0 or next_chapter < previous_chapter:
                        raise ValueError(
                            f"invalid chapter order in {document.member.filename}: {next_chapter}"
                        )
                    chapter = next_chapter
                    previous_chapter = next_chapter
                    continue

                verse_match = VERSE_RE.match(stripped)
                if verse_match:
                    if chapter is None:
                        raise ValueError(
                            f"verse before chapter in {document.member.filename}: {stripped}"
                        )
                    pending = flush()
                    if pending is not None:
                        yield pending
                    label = verse_match.group("label")
                    locus = (chapter, label)
                    if locus in seen_loci:
                        raise ValueError(
                            f"duplicate verse locus in {document.book_code}: {chapter}:{label}"
                        )
                    seen_loci.add(locus)
                    current_label = label
                    payload = verse_match.group("payload")
                    current_payload = [] if payload is None else [payload]
                    continue

                if current_label is not None:
                    current_payload.append(line)

            pending = flush()
            if pending is not None:
                yield pending

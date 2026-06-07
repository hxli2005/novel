"""Chapter parsing for source novels."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

MIN_CHAPTER_COUNT = 3

CHAPTER_HEADING_PATTERN = re.compile(
    r"""
    ^\s*
    (?:
        \#{1,6}\s*
    )?
    (?P<title>
        (?:
            第[一二三四五六七八九十百千万零〇两\d]+[章节卷回部集]
            [^\n]{0,80}
        )
        |
        (?:
            Chapter\s+\d+
            [^\n]{0,80}
        )
    )
    \s*$
    """,
    re.IGNORECASE | re.MULTILINE | re.VERBOSE,
)


@dataclass(frozen=True)
class ParsedChapter:
    """A parsed chapter with source text and stable metadata."""

    id: str
    order: int
    title: str
    text: str
    word_count: int
    text_hash: str
    summary: str = ""


class ChapterParseError(ValueError):
    """Raised when chapter parsing cannot produce a valid document."""


def parse_chapters(source_text: str) -> list[ParsedChapter]:
    """Parse source text into chapters.

    Chapter headings support common Chinese forms such as ``第一章 标题`` and
    Markdown headings such as ``# 第一章 标题``. English ``Chapter 1`` headings
    are accepted for fixtures and future multilingual inputs.
    """

    normalized_text = source_text.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(_iter_heading_matches(normalized_text))
    if not matches:
        raise ChapterParseError("No chapter headings were found.")

    chapters: list[ParsedChapter] = []
    for index, match in enumerate(matches):
        next_start = (
            matches[index + 1].start() if index + 1 < len(matches) else len(normalized_text)
        )
        body_start = match.end()
        title = match.group("title").strip()
        body = normalized_text[body_start:next_start].strip()
        chapter_text = f"{title}\n\n{body}".strip()
        order = index + 1
        chapters.append(
            ParsedChapter(
                id=f"ch_{order:03d}",
                order=order,
                title=title,
                text=chapter_text,
                word_count=count_cjk_aware_words(chapter_text),
                text_hash=f"sha256:{hashlib.sha256(chapter_text.encode('utf-8')).hexdigest()}",
            )
        )

    if len(chapters) < MIN_CHAPTER_COUNT:
        raise ChapterParseError(
            f"At least {MIN_CHAPTER_COUNT} chapters are required; found {len(chapters)}."
        )
    return chapters


# utf-8-sig also decodes plain UTF-8 (it just strips a leading BOM if present),
# so it covers the UTF-8 case; GB18030 is a superset of GBK/GB2312.
SOURCE_ENCODINGS = ("utf-8-sig", "gb18030")


def read_source_text(source_path: Path) -> str:
    """Read a novel file, tolerating common Chinese encodings.

    Many Chinese novels are saved as GBK/GB2312 rather than UTF-8, so a strict
    UTF-8 read raises UnicodeDecodeError. Try UTF-8 (with optional BOM) first,
    then GB18030 (a superset of GBK/GB2312); fall back to a lossy UTF-8 read so
    parsing never crashes on an unknown encoding.
    """

    raw = source_path.read_bytes()
    for encoding in SOURCE_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_chapters_file(source_path: Path) -> list[ParsedChapter]:
    """Read and parse chapters from a text file."""

    return parse_chapters(read_source_text(source_path))


def write_parsed_chapters_yaml(chapters: list[ParsedChapter], output_path: Path) -> None:
    """Write parsed chapter metadata to a small YAML document."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["chapters:"]
    for chapter in chapters:
        lines.extend(
            [
                f"  - id: {quote_yaml_scalar(chapter.id)}",
                f"    order: {chapter.order}",
                f"    title: {quote_yaml_scalar(chapter.title)}",
                f"    word_count: {chapter.word_count}",
                f"    text_hash: {quote_yaml_scalar(chapter.text_hash)}",
                f"    summary: {quote_yaml_scalar(chapter.summary)}",
            ]
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def count_cjk_aware_words(text: str) -> int:
    """Count Chinese characters and non-CJK word tokens for rough sizing."""

    cjk_chars = re.findall(r"[\u3400-\u9fff]", text)
    non_cjk_words = re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text)
    return len(cjk_chars) + len(non_cjk_words)


def quote_yaml_scalar(value: str) -> str:
    """Quote a scalar string for the limited YAML emitted by this module."""

    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _iter_heading_matches(text: str) -> Iterable[re.Match[str]]:
    return CHAPTER_HEADING_PATTERN.finditer(text)

import pytest

from novel_to_screenplay.pipeline.chapter_parser import ChapterParseError, parse_chapters
from novel_to_screenplay.runner import select_chapters


def _chapters(count: int):
    text = "\n\n".join(f"第{i}章 标题{i}\n正文内容{i}。" for i in range(1, count + 1))
    return parse_chapters(text)


def test_select_chapters_returns_inclusive_range() -> None:
    selected = select_chapters(_chapters(6), 2, 4)
    assert [chapter.order for chapter in selected] == [2, 3, 4]


def test_select_chapters_runs_to_end_when_end_is_none() -> None:
    selected = select_chapters(_chapters(6), 4, None)
    assert [chapter.order for chapter in selected] == [4, 5, 6]


def test_select_chapters_rejects_range_below_minimum() -> None:
    with pytest.raises(ChapterParseError):
        select_chapters(_chapters(6), 1, 2)

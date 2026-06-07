import pytest

from novel_to_screenplay.pipeline.chapter_parser import (
    ChapterParseError,
    parse_chapters,
    parse_chapters_file,
)


def test_parse_chapters_file_reads_gbk_encoding(tmp_path) -> None:  # type: ignore[no-untyped-def]
    source = tmp_path / "novel.txt"
    text = "第一章 起\n中文内容。\n\n第二章 承\n更多内容。\n\n第三章 合\n结尾。\n"
    source.write_bytes(text.encode("gbk"))

    chapters = parse_chapters_file(source)

    assert len(chapters) == 3
    assert chapters[0].title == "第一章 起"


def test_parse_chapters_supports_markdown_chinese_headings() -> None:
    chapters = parse_chapters(
        "\n\n".join(
            [
                "# 第一章 开端\n主角发现线索。",
                "# 第二章 调查\n主角进入旧楼。",
                "# 第三章 揭露\n真相浮出水面。",
            ]
        )
    )

    assert [chapter.id for chapter in chapters] == ["ch_001", "ch_002", "ch_003"]
    assert chapters[0].title == "第一章 开端"
    assert chapters[0].text.startswith("第一章 开端")
    assert chapters[0].word_count > 0
    assert chapters[0].text_hash.startswith("sha256:")


def test_parse_chapters_rejects_missing_headings() -> None:
    with pytest.raises(ChapterParseError, match="No chapter headings"):
        parse_chapters("这里只是一段没有章节标题的小说。")


def test_parse_chapters_rejects_less_than_three_chapters() -> None:
    with pytest.raises(ChapterParseError, match="At least 3 chapters"):
        parse_chapters("第一章 开端\n内容。\n\n第二章 继续\n内容。")

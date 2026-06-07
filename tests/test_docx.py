from pathlib import Path

from docx import Document

from novel_to_screenplay.exporters import write_docx


def build_document() -> dict:
    return {
        "metadata": {"title": "第七页", "author": "示例作者"},
        "scenes": [
            {
                "id": "sc_001",
                "scene_heading": {
                    "location_mode": "INT",
                    "display": "档案室",
                    "time_of_day": "NIGHT",
                },
                "script": [
                    {"type": "action", "text": "林青翻开档案。"},
                    {
                        "type": "dialogue",
                        "character_id": "char_001",
                        "character_name": "林青",
                        "text": "我们不能再等了。",
                        "parenthetical": "压低声音",
                        "subtext": "她在害怕。",
                    },
                    {
                        "type": "voiceover",
                        "character_id": "char_001",
                        "character_name": "林青",
                        "text": "那一夜我没能合眼。",
                    },
                    {"type": "note", "text": "需作者复核节奏。"},
                ],
            }
        ],
    }


def test_write_docx_creates_readable_document(tmp_path: Path) -> None:
    output_path = tmp_path / "screenplay.docx"

    write_docx(build_document(), output_path)

    assert output_path.is_file()
    text = "\n".join(paragraph.text for paragraph in Document(str(output_path)).paragraphs)
    assert "第七页" in text
    assert "编剧：示例作者" in text
    assert "INT. 档案室 - 夜" in text
    assert "林青：" in text
    assert "（压低声音）" in text
    assert "我们不能再等了。" in text
    assert "潜台词：她在害怕。" in text
    assert "林青（V.O.）：" in text
    assert "【批注】需作者复核节奏。" in text

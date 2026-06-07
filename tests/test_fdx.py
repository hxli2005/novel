import xml.etree.ElementTree as ET
from pathlib import Path

from novel_to_screenplay.exporters import to_fdx, write_fdx


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
                    {"type": "note", "text": "需作者复核节奏。"},
                ],
            },
            {
                "id": "sc_002",
                "scene_heading": {
                    "location_mode": "UNKNOWN",
                    "display": "走廊",
                    "time_of_day": "UNKNOWN",
                },
                "script": [
                    {
                        "type": "voiceover",
                        "character_id": "char_001",
                        "character_name": "林青",
                        "text": "那一夜我没能合眼。",
                    },
                    {"type": "transition", "text": "切至："},
                ],
            },
        ],
    }


def test_to_fdx_is_well_formed_and_maps_paragraph_types() -> None:
    xml = to_fdx(build_document())
    assert xml.startswith("<?xml")

    root = ET.fromstring(xml)  # raises on malformed XML
    assert root.tag == "FinalDraft"
    assert root.get("DocumentType") == "Script"

    content = root.find("Content")
    assert content is not None
    paragraphs = [(p.get("Type"), p.findtext("Text") or "") for p in content.findall("Paragraph")]

    # Scene headings: INT/NIGHT renders with mode + time; UNKNOWN/UNKNOWN is bare.
    assert ("Scene Heading", "内 档案室 - 夜") in paragraphs
    assert ("Scene Heading", "走廊") in paragraphs
    # Action, dialogue, parenthetical.
    assert ("Action", "林青翻开档案。") in paragraphs
    assert ("Character", "林青") in paragraphs
    assert ("Parenthetical", "（压低声音）") in paragraphs
    assert ("Dialogue", "我们不能再等了。") in paragraphs
    # Subtext + note have no native FDX type, so they survive as marked Action.
    assert ("Action", "（潜台词：她在害怕。）") in paragraphs
    assert ("Action", "需作者复核节奏。") in paragraphs
    # Voiceover becomes a character extension; transition keeps its type.
    assert ("Character", "林青（V.O.）") in paragraphs
    assert ("Transition", "切至：") in paragraphs


def test_to_fdx_includes_title_page() -> None:
    root = ET.fromstring(to_fdx(build_document()))
    title_page = root.find("TitlePage")
    assert title_page is not None
    texts = [p.findtext("Text") for p in title_page.iter("Paragraph")]
    assert "第七页" in texts
    assert "编剧：示例作者" in texts


def test_write_fdx_writes_parseable_file(tmp_path: Path) -> None:
    output_path = tmp_path / "screenplay.fdx"
    write_fdx(build_document(), output_path)
    assert output_path.is_file()
    ET.parse(output_path)  # parses without error

from novel_to_screenplay.exporters import to_fountain


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


def test_to_fountain_renders_title_page_and_scene_headings() -> None:
    text = to_fountain(build_document())

    assert text.startswith("Title: 第七页")
    assert "Author: 示例作者" in text
    assert "INT. 档案室 - 夜" in text
    # Unknown location mode is a forced heading; unknown time is omitted.
    assert ".走廊" in text
    assert ".走廊 -" not in text


def test_to_fountain_renders_dialogue_and_markers() -> None:
    text = to_fountain(build_document())

    assert "@林青" in text  # forced character cue (Chinese names have no case)
    assert "(压低声音)" in text
    assert "我们不能再等了。" in text
    assert "[[潜台词：她在害怕。]]" in text
    assert "[[需作者复核节奏。]]" in text
    assert "@林青 (V.O.)" in text
    assert "> 切至：" in text

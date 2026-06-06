from novel_to_screenplay.pipeline.consistency import (
    analyze_consistency,
    apply_consistency_findings,
)


def build_document() -> dict:
    return {
        "source": {
            "chapters": [
                {"id": "ch_001", "title": "起"},
                {"id": "ch_002", "title": "承"},
                {"id": "ch_003", "title": "合"},
            ]
        },
        "characters": [
            {"id": "char_001", "name": "甲"},
            {"id": "char_002", "name": "乙"},
            {"id": "char_003", "name": "丙"},
        ],
        "scenes": [
            {
                "id": "sc_001",
                "chapter_refs": ["ch_001"],
                "characters_present": ["char_001", "char_002"],
                "script": [
                    {"type": "action", "text": "甲与乙对峙。"},
                    {"type": "dialogue", "character_id": "char_001", "text": "我来了。"},
                ],
            },
            {
                "id": "sc_002",
                "chapter_refs": ["ch_002"],
                "characters_present": ["char_001"],
                "script": [
                    {"type": "dialogue", "character_id": "char_001", "text": "继续。"},
                ],
            },
        ],
        "quality_report": {"validation_status": "pass", "warnings": []},
    }


def test_analyze_consistency_reports_each_issue_type() -> None:
    findings = analyze_consistency(build_document())
    codes = {finding.code for finding in findings}

    # ch_003 is never adapted; char_003 never appears; char_002 appears but is silent.
    assert "CHAPTER_NOT_ADAPTED" in codes
    assert "CHARACTER_UNUSED" in codes
    assert "CHARACTER_NO_DIALOGUE" in codes

    silent = next(f for f in findings if f.code == "CHARACTER_NO_DIALOGUE")
    assert silent.scene_id == "sc_001"


def test_analyze_consistency_clean_document_has_no_findings() -> None:
    document = build_document()
    # Adapt the last chapter, give the silent/unused characters presence and a line.
    document["scenes"][1]["chapter_refs"] = ["ch_002", "ch_003"]
    document["scenes"][0]["script"].append(
        {"type": "dialogue", "character_id": "char_002", "text": "我也在。"}
    )
    document["scenes"][1]["characters_present"] = ["char_001", "char_003"]
    document["scenes"][1]["script"].append(
        {"type": "dialogue", "character_id": "char_003", "text": "我登场了。"}
    )

    assert analyze_consistency(document) == []


def test_unused_check_treats_script_speakers_as_present() -> None:
    document = build_document()
    # char_003 is absent from every characters_present but speaks in a scene;
    # a schema-valid document can be this slightly inconsistent.
    document["scenes"][0]["script"].append(
        {"type": "dialogue", "character_id": "char_003", "text": "我只在台词里出现。"}
    )

    findings = analyze_consistency(document)

    unused_messages = [f.message for f in findings if f.code == "CHARACTER_UNUSED"]
    assert all("char_003" not in message for message in unused_messages)


def test_apply_consistency_findings_updates_quality_report() -> None:
    document = build_document()
    findings = analyze_consistency(document)

    apply_consistency_findings(document, findings)

    warnings = document["quality_report"]["warnings"]
    assert len(warnings) == len(findings)
    assert document["quality_report"]["validation_status"] == "warning"
    assert all("code" in warning and "message" in warning for warning in warnings)


def test_apply_consistency_findings_is_idempotent() -> None:
    document = build_document()
    findings = analyze_consistency(document)

    apply_consistency_findings(document, findings)
    apply_consistency_findings(document, findings)

    warnings = document["quality_report"]["warnings"]
    assert len(warnings) == len(findings)

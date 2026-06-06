"""Validation for generated screenplay YAML files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class ValidationIssue:
    """One schema or reference validation issue."""

    code: str
    message: str
    path: str


@dataclass(frozen=True)
class ValidationResult:
    """Validation summary for a screenplay YAML file."""

    screenplay_path: Path
    schema_path: Path
    issues: list[ValidationIssue]

    @property
    def passed(self) -> bool:
        """Return whether validation found no blocking issue."""

        return not self.issues


def validate_screenplay_file(
    screenplay_path: Path,
    schema_path: Path,
) -> ValidationResult:
    """Validate a screenplay YAML file against schema and ID references."""

    document = load_yaml_document(screenplay_path)
    schema = load_json_schema(schema_path)
    issues = validate_json_schema(document, schema)
    if isinstance(document, dict):
        issues.extend(validate_id_references(document))
    return ValidationResult(
        screenplay_path=screenplay_path,
        schema_path=schema_path,
        issues=issues,
    )


def load_yaml_document(screenplay_path: Path) -> Any:
    """Load a YAML document from disk."""

    with screenplay_path.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_json_schema(schema_path: Path) -> dict[str, Any]:
    """Load the screenplay JSON Schema from disk."""

    with schema_path.open(encoding="utf-8") as file:
        schema = json.load(file)
    if not isinstance(schema, dict):
        raise ValueError(f"Schema must be a JSON object: {schema_path}")
    return schema


def validate_json_schema(document: Any, schema: dict[str, Any]) -> list[ValidationIssue]:
    """Validate a document with JSON Schema."""

    validator = Draft202012Validator(schema)
    return [
        ValidationIssue(
            code="SCHEMA_ERROR",
            message=error.message,
            path=format_path(error.absolute_path),
        )
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    ]


def validate_id_references(document: dict[str, Any]) -> list[ValidationIssue]:
    """Validate cross-field ID references not expressible in JSON Schema."""

    issues: list[ValidationIssue] = []
    chapter_ids = collect_ids(document.get("source", {}).get("chapters", []))
    character_ids = collect_ids(document.get("characters", []))
    location_ids = collect_ids(document.get("locations", []))
    scenes = document.get("scenes", [])
    scene_ids = collect_ids(scenes)
    key_events = document.get("structure", {}).get("key_events", [])
    key_event_ids = collect_ids(key_events)

    for scene_index, scene in enumerate(scenes if isinstance(scenes, list) else []):
        scene_path = f"/scenes/{scene_index}"
        check_id_list(
            issues,
            scene.get("chapter_refs", []),
            chapter_ids,
            "UNKNOWN_CHAPTER_REF",
            f"{scene_path}/chapter_refs",
        )
        heading = scene.get("scene_heading", {})
        location_id = heading.get("location_id")
        if location_id:
            check_id(
                issues,
                location_id,
                location_ids,
                "UNKNOWN_LOCATION_REF",
                f"{scene_path}/scene_heading/location_id",
            )
        check_id_list(
            issues,
            scene.get("characters_present", []),
            character_ids,
            "UNKNOWN_CHARACTER_REF",
            f"{scene_path}/characters_present",
        )
        for beat_index, beat in enumerate(scene.get("beats", [])):
            check_source_refs(
                issues,
                beat.get("source_refs", []),
                chapter_ids,
                f"{scene_path}/beats/{beat_index}/source_refs",
            )
        for script_index, element in enumerate(scene.get("script", [])):
            character_id = element.get("character_id")
            if character_id:
                check_id(
                    issues,
                    character_id,
                    character_ids,
                    "UNKNOWN_CHARACTER_REF",
                    f"{scene_path}/script/{script_index}/character_id",
                )
            check_source_refs(
                issues,
                element.get("source_refs", []),
                chapter_ids,
                f"{scene_path}/script/{script_index}/source_refs",
            )
        continuity = scene.get("continuity", {})
        for field_name in ("previous_scene_id", "next_scene_id"):
            scene_ref = continuity.get(field_name)
            if scene_ref:
                check_id(
                    issues,
                    scene_ref,
                    scene_ids,
                    "UNKNOWN_SCENE_REF",
                    f"{scene_path}/continuity/{field_name}",
                )

    structure = document.get("structure", {})
    for act_index, act in enumerate(structure.get("acts", [])):
        check_id_list(
            issues,
            act.get("scene_ids", []),
            scene_ids,
            "UNKNOWN_SCENE_REF",
            f"/structure/acts/{act_index}/scene_ids",
        )
    for event_index, event in enumerate(key_events if isinstance(key_events, list) else []):
        event_path = f"/structure/key_events/{event_index}"
        check_id_list(
            issues,
            event.get("chapter_refs", []),
            chapter_ids,
            "UNKNOWN_CHAPTER_REF",
            f"{event_path}/chapter_refs",
        )
        check_id_list(
            issues,
            event.get("scene_ids", []),
            scene_ids,
            "UNKNOWN_SCENE_REF",
            f"{event_path}/scene_ids",
        )
        check_id_list(
            issues,
            event.get("causal_links", []),
            key_event_ids,
            "UNKNOWN_EVENT_REF",
            f"{event_path}/causal_links",
        )

    quality_report = document.get("quality_report", {})
    for coverage_index, coverage in enumerate(quality_report.get("chapter_coverage", [])):
        coverage_path = f"/quality_report/chapter_coverage/{coverage_index}"
        check_id(
            issues,
            coverage.get("chapter_id"),
            chapter_ids,
            "UNKNOWN_CHAPTER_REF",
            f"{coverage_path}/chapter_id",
        )
        check_id_list(
            issues,
            coverage.get("used_in_scene_ids", []),
            scene_ids,
            "UNKNOWN_SCENE_REF",
            f"{coverage_path}/used_in_scene_ids",
        )

    return issues


def collect_ids(items: Any) -> set[str]:
    """Collect IDs from a list of dictionaries."""

    if not isinstance(items, list):
        return set()
    return {
        item["id"] for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def check_id(
    issues: list[ValidationIssue],
    value: Any,
    known_ids: set[str],
    code: str,
    path: str,
) -> None:
    """Append an issue if a scalar ID is unknown."""

    if isinstance(value, str) and value not in known_ids:
        issues.append(
            ValidationIssue(
                code=code,
                message=f"Unknown ID reference: {value}",
                path=path,
            )
        )


def check_id_list(
    issues: list[ValidationIssue],
    values: Any,
    known_ids: set[str],
    code: str,
    path: str,
) -> None:
    """Append issues for unknown IDs in a list."""

    if not isinstance(values, list):
        return
    for index, value in enumerate(values):
        check_id(issues, value, known_ids, code, f"{path}/{index}")


def check_source_refs(
    issues: list[ValidationIssue],
    source_refs: Any,
    chapter_ids: set[str],
    path: str,
) -> None:
    """Validate chapter IDs inside source refs."""

    if not isinstance(source_refs, list):
        return
    for index, source_ref in enumerate(source_refs):
        if not isinstance(source_ref, dict):
            continue
        check_id(
            issues,
            source_ref.get("chapter_id"),
            chapter_ids,
            "UNKNOWN_CHAPTER_REF",
            f"{path}/{index}/chapter_id",
        )


def format_path(path_parts: Any) -> str:
    """Format a jsonschema path as a slash path."""

    parts = list(path_parts)
    if not parts:
        return "/"
    return "/" + "/".join(str(part) for part in parts)

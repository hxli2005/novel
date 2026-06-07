"""Shared pipeline orchestration used by both the CLI and the web UI.

Keeping the parse -> analyze -> outline -> generate -> draft -> validate
sequence in one place avoids logic drift between entry points. ``on_event``
receives a dict per stage transition so a caller (e.g. the web UI) can stream
progress; the CLI passes nothing and reads the returned result.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from novel_to_screenplay.pipeline.chapter_parser import (
    MIN_CHAPTER_COUNT,
    ChapterParseError,
    ParsedChapter,
    parse_chapters_file,
    write_parsed_chapters_yaml,
)
from novel_to_screenplay.pipeline.entity_analyzer import (
    EntityAnalysis,
    analyze_chapters_auto,
    write_entity_analysis_outputs,
)
from novel_to_screenplay.pipeline.scene_drafter import SceneDraftResult, draft_screenplay_scenes
from novel_to_screenplay.pipeline.scene_outliner import (
    SceneOutline,
    build_scene_outline_auto,
    write_scene_outline_yaml,
)
from novel_to_screenplay.pipeline.screenplay_generator import (
    ScreenplayGenerationOptions,
    build_screenplay_document,
    write_screenplay_yaml,
)
from novel_to_screenplay.pipeline.screenplay_validator import (
    ValidationResult,
    validate_screenplay_file,
)
from novel_to_screenplay.workspace import WorkspaceLayout

EventCallback = Callable[[dict[str, Any]], None]


@dataclass
class PipelineResult:
    """Outcome of a full pipeline run."""

    chapters: list[ParsedChapter]
    analysis: EntityAnalysis
    outline: SceneOutline
    screenplay_path: Path
    draft_result: SceneDraftResult
    validation: ValidationResult | None
    total_chapters: int
    chapter_start: int
    chapter_end: int


def select_chapters(
    chapters: list[ParsedChapter],
    chapter_start: int,
    chapter_end: int | None,
) -> list[ParsedChapter]:
    """Return chapters in the 1-based inclusive [start, end] range.

    Lets a user convert only part of a long novel. The selection must still hold
    at least MIN_CHAPTER_COUNT chapters (the screenplay schema's minimum).
    """

    start = max(1, chapter_start)
    selected = chapters[start - 1 : chapter_end]
    if len(selected) < MIN_CHAPTER_COUNT:
        message = (
            f"所选章节范围不足 {MIN_CHAPTER_COUNT} 章"
            f"（原著共解析 {len(chapters)} 章），请扩大范围。"
        )
        raise ChapterParseError(message)
    return selected


def run_pipeline(
    staged_path: Path,
    layout: WorkspaceLayout,
    provider: Any,
    options: ScreenplayGenerationOptions,
    *,
    outline_adaptation: dict[str, str] | None = None,
    max_tokens: int = 2048,
    schema: Path | None = None,
    on_event: EventCallback | None = None,
    chapter_start: int = 1,
    chapter_end: int | None = None,
) -> PipelineResult:
    """Run the full conversion pipeline over an already-staged source file.

    ``chapter_start`` / ``chapter_end`` (1-based, inclusive) restrict the run to
    part of a long novel; by default the whole novel is converted.
    """

    def emit(stage: str, status: str, **fields: Any) -> None:
        if on_event is not None:
            on_event({"stage": stage, "status": status, **fields})

    emit("parse", "start")
    try:
        all_chapters = parse_chapters_file(staged_path)
        chapters = select_chapters(all_chapters, chapter_start, chapter_end)
    except Exception as exc:  # noqa: BLE001 - surface the failure, then re-raise
        emit("parse", "error", message=str(exc))
        raise
    write_parsed_chapters_yaml(chapters, layout.intermediates_dir / "parsed_chapters.yaml")
    emit("parse", "done", count=len(chapters), total=len(all_chapters))

    emit("analyze", "start")
    analysis = analyze_chapters_auto(chapters, provider)
    write_entity_analysis_outputs(analysis, layout.intermediates_dir)
    emit(
        "analyze",
        "done",
        characters=len(analysis.characters),
        locations=len(analysis.locations),
    )

    emit("outline", "start")
    outline = build_scene_outline_auto(analysis, provider, adaptation=outline_adaptation)
    write_scene_outline_yaml(outline, layout.intermediates_dir / "scene_outline.yaml")
    emit("outline", "done", count=len(outline.scenes))

    emit("generate", "start")
    screenplay = build_screenplay_document(chapters, analysis, outline, options)
    screenplay_path = layout.output_dir / "screenplay.yaml"
    write_screenplay_yaml(screenplay, screenplay_path)
    emit("generate", "done", scenes=len(outline.scenes))

    emit("draft", "start", total=len(screenplay.get("scenes", [])))
    draft_result = draft_screenplay_scenes(
        screenplay,
        provider,
        max_tokens=max_tokens,
        on_scene=lambda index, total, scene_id: emit(
            "draft", "progress", index=index, total=total, scene_id=scene_id
        ),
    )
    write_screenplay_yaml(draft_result.document, screenplay_path)
    emit("draft", "done", count=len(draft_result.drafted_scene_ids))

    validation: ValidationResult | None = None
    if schema is not None and schema.is_file():
        emit("validate", "start")
        validation = validate_screenplay_file(screenplay_path, schema)
        emit(
            "validate",
            "done" if validation.passed else "fail",
            issues=0 if validation.passed else len(validation.issues),
        )

    return PipelineResult(
        chapters=chapters,
        analysis=analysis,
        outline=outline,
        screenplay_path=screenplay_path,
        draft_result=draft_result,
        validation=validation,
        total_chapters=len(all_chapters),
        chapter_start=max(1, chapter_start),
        chapter_end=chapter_end if chapter_end is not None else len(all_chapters),
    )

"""Command line interface for the novel-to-screenplay tool."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from novel_to_screenplay import __version__
from novel_to_screenplay.pipeline.chapter_parser import (
    ChapterParseError,
    parse_chapters_file,
    write_parsed_chapters_yaml,
)
from novel_to_screenplay.pipeline.entity_analyzer import (
    analyze_chapters,
    write_entity_analysis_outputs,
)
from novel_to_screenplay.pipeline.scene_outliner import (
    build_scene_outline,
    write_scene_outline_yaml,
)
from novel_to_screenplay.pipeline.screenplay_generator import (
    ScreenplayGenerationOptions,
    build_screenplay_document,
    write_screenplay_yaml,
)
from novel_to_screenplay.workspace import (
    build_workspace_layout,
    find_staged_source_file,
    initialize_workspace,
    stage_source_file,
)

SUPPORTED_INPUT_SUFFIXES = {".txt", ".md"}

app = typer.Typer(
    help="Convert multi-chapter novels into structured screenplay YAML drafts.",
    invoke_without_command=True,
    no_args_is_help=True,
)
console = Console()


def _validate_input_path(input_path: Path) -> Path:
    if input_path.suffix.lower() not in SUPPORTED_INPUT_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_INPUT_SUFFIXES))
        raise typer.BadParameter(f"input file must use one of: {supported}")
    return input_path


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option("--version", help="Show the CLI version and exit."),
    ] = False,
) -> None:
    """AI-assisted novel-to-screenplay conversion pipeline."""

    if version:
        console.print(f"novel2script {__version__}")
        raise typer.Exit()


@app.command()
def status() -> None:
    """Print the current CLI readiness status."""

    console.print("novel2script pipeline is ready through screenplay YAML draft generation.")


@app.command()
def run(
    input_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Path to a .txt or .md novel file.",
        ),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Output workspace directory."),
    ] = Path("runs/demo"),
    provider: Annotated[
        str,
        typer.Option("--provider", help="LLM provider name."),
    ] = "mock",
    title: Annotated[
        str,
        typer.Option("--title", help="Title written into the generated screenplay YAML."),
    ] = "剧本初稿",
    author: Annotated[
        str,
        typer.Option("--author", help="Author or adapter name written into metadata."),
    ] = "待填写",
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate inputs without writing output files."),
    ] = False,
) -> None:
    """Run the available local conversion pipeline stages."""

    input_path = _validate_input_path(input_path)

    if dry_run:
        console.print(
            f"Ready to run with provider '{provider}' using input '{input_path}'.",
        )
        return

    layout = initialize_workspace(out)
    staged_path = stage_source_file(input_path, layout)
    try:
        chapters = parse_chapters_file(staged_path)
    except ChapterParseError as exc:
        raise typer.BadParameter(str(exc)) from exc

    parsed_chapters_path = layout.intermediates_dir / "parsed_chapters.yaml"
    write_parsed_chapters_yaml(chapters, parsed_chapters_path)

    analysis = analyze_chapters(chapters)
    write_entity_analysis_outputs(analysis, layout.intermediates_dir)
    outline = build_scene_outline(analysis)
    scene_outline_path = layout.intermediates_dir / "scene_outline.yaml"
    write_scene_outline_yaml(outline, scene_outline_path)
    screenplay = build_screenplay_document(
        chapters,
        analysis,
        outline,
        ScreenplayGenerationOptions(title=title, author=author),
    )
    screenplay_path = layout.output_dir / "screenplay.yaml"
    write_screenplay_yaml(screenplay, screenplay_path)

    console.print(f"Initialized workspace: {layout.root}")
    console.print(f"Staged source: {staged_path}")
    console.print(f"Parsed chapters: {len(chapters)}")
    console.print(f"Analyzed chapters: {len(analysis.chapter_analyses)}")
    console.print(f"Outlined scenes: {len(outline.scenes)}")
    console.print(f"Generated screenplay: {screenplay_path}")
    console.print(f"Extracted characters: {len(analysis.characters)}")
    console.print(f"Extracted locations: {len(analysis.locations)}")
    console.print(f"Provider: {provider}")


@app.command()
def parse(
    input_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Path to a .txt or .md novel file.",
        ),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Output workspace directory."),
    ] = Path("runs/demo"),
) -> None:
    """Parse novel chapters and write parsed_chapters.yaml."""

    input_path = _validate_input_path(input_path)
    layout = initialize_workspace(out)
    staged_path = stage_source_file(input_path, layout)

    try:
        chapters = parse_chapters_file(staged_path)
    except ChapterParseError as exc:
        raise typer.BadParameter(str(exc)) from exc

    output_path = layout.intermediates_dir / "parsed_chapters.yaml"
    write_parsed_chapters_yaml(chapters, output_path)
    console.print(f"Parsed chapters: {len(chapters)}")
    console.print(f"Wrote: {output_path}")


@app.command()
def analyze(
    workspace: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            readable=True,
            help="Workspace directory produced by `novel2script parse`.",
        ),
    ] = Path("runs/demo"),
) -> None:
    """Extract first-pass entities and chapter analysis files."""

    layout = build_workspace_layout(workspace)
    try:
        staged_path = find_staged_source_file(layout)
    except FileNotFoundError as exc:
        console.print("No staged source file found. Run novel2script parse first.")
        raise typer.Exit(1) from exc

    try:
        chapters = parse_chapters_file(staged_path)
    except ChapterParseError as exc:
        raise typer.BadParameter(str(exc)) from exc

    analysis = analyze_chapters(chapters)
    write_entity_analysis_outputs(analysis, layout.intermediates_dir)

    console.print(f"Analyzed chapters: {len(analysis.chapter_analyses)}")
    console.print(f"Extracted characters: {len(analysis.characters)}")
    console.print(f"Extracted locations: {len(analysis.locations)}")
    console.print(f"Wrote: {layout.intermediates_dir / 'chapter_analysis.yaml'}")


@app.command()
def outline(
    workspace: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            readable=True,
            help="Workspace directory produced by `novel2script parse`.",
        ),
    ] = Path("runs/demo"),
) -> None:
    """Generate a first-pass scene outline file."""

    layout = build_workspace_layout(workspace)
    try:
        staged_path = find_staged_source_file(layout)
    except FileNotFoundError as exc:
        console.print("No staged source file found. Run novel2script parse first.")
        raise typer.Exit(1) from exc

    try:
        chapters = parse_chapters_file(staged_path)
    except ChapterParseError as exc:
        raise typer.BadParameter(str(exc)) from exc

    analysis = analyze_chapters(chapters)
    outline_result = build_scene_outline(analysis)
    output_path = layout.intermediates_dir / "scene_outline.yaml"
    write_scene_outline_yaml(outline_result, output_path)

    console.print(f"Outlined scenes: {len(outline_result.scenes)}")
    console.print(f"Wrote: {output_path}")


@app.command()
def generate(
    workspace: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            readable=True,
            help="Workspace directory produced by `novel2script parse`.",
        ),
    ] = Path("runs/demo"),
    title: Annotated[
        str,
        typer.Option("--title", help="Title written into the generated screenplay YAML."),
    ] = "剧本初稿",
    author: Annotated[
        str,
        typer.Option("--author", help="Author or adapter name written into metadata."),
    ] = "待填写",
) -> None:
    """Generate output/screenplay.yaml from the current pipeline stages."""

    layout = build_workspace_layout(workspace)
    layout.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        staged_path = find_staged_source_file(layout)
    except FileNotFoundError as exc:
        console.print("No staged source file found. Run novel2script parse first.")
        raise typer.Exit(1) from exc

    try:
        chapters = parse_chapters_file(staged_path)
    except ChapterParseError as exc:
        raise typer.BadParameter(str(exc)) from exc

    analysis = analyze_chapters(chapters)
    outline_result = build_scene_outline(analysis)
    screenplay = build_screenplay_document(
        chapters,
        analysis,
        outline_result,
        ScreenplayGenerationOptions(title=title, author=author),
    )
    output_path = layout.output_dir / "screenplay.yaml"
    write_screenplay_yaml(screenplay, output_path)

    console.print(f"Generated screenplay: {output_path}")
    console.print(f"Scenes: {len(outline_result.scenes)}")


def main() -> None:
    """Entrypoint used by the console script."""

    app()


if __name__ == "__main__":
    main()

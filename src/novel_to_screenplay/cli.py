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
from novel_to_screenplay.pipeline.consistency import (
    analyze_consistency,
    apply_consistency_findings,
)
from novel_to_screenplay.pipeline.entity_analyzer import (
    analyze_chapters,
    write_entity_analysis_outputs,
)
from novel_to_screenplay.pipeline.scene_drafter import draft_screenplay_scenes
from novel_to_screenplay.pipeline.scene_outliner import (
    build_scene_outline,
    write_scene_outline_yaml,
)
from novel_to_screenplay.pipeline.screenplay_generator import (
    ScreenplayGenerationOptions,
    build_screenplay_document,
    write_screenplay_yaml,
)
from novel_to_screenplay.pipeline.screenplay_validator import (
    load_yaml_document,
    validate_screenplay_file,
)
from novel_to_screenplay.providers import (
    ChatMessage,
    ProviderError,
    build_provider,
    get_provider_statuses,
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


def _validate_provider_name(provider: str) -> str:
    try:
        build_provider(provider, env={"DEEPSEEK_API_KEY": "placeholder"})
    except ProviderError as exc:
        raise typer.BadParameter(str(exc)) from exc
    return provider


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
        typer.Option("--provider", help="LLM provider used to draft scene scripts."),
    ] = "mock",
    title: Annotated[
        str,
        typer.Option("--title", help="Title written into the generated screenplay YAML."),
    ] = "剧本初稿",
    author: Annotated[
        str,
        typer.Option("--author", help="Author or adapter name written into metadata."),
    ] = "待填写",
    max_tokens: Annotated[
        int,
        typer.Option("--max-tokens", min=1, help="Maximum tokens per drafted scene."),
    ] = 2048,
    schema: Annotated[
        Path,
        typer.Option("--schema", help="Path to the screenplay JSON Schema file."),
    ] = Path("schemas/screenplay.schema.json"),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate inputs without writing output files."),
    ] = False,
) -> None:
    """Run the full pipeline: parse, analyze, outline, generate, draft, and validate."""

    input_path = _validate_input_path(input_path)
    provider = _validate_provider_name(provider)

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

    try:
        llm_provider = build_provider(provider)
        draft_result = draft_screenplay_scenes(
            screenplay,
            llm_provider,
            max_tokens=max_tokens,
        )
    except ProviderError as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc
    write_screenplay_yaml(draft_result.document, screenplay_path)

    console.print(f"Initialized workspace: {layout.root}")
    console.print(f"Staged source: {staged_path}")
    console.print(f"Parsed chapters: {len(chapters)}")
    console.print(f"Analyzed chapters: {len(analysis.chapter_analyses)}")
    console.print(f"Outlined scenes: {len(outline.scenes)}")
    console.print(f"Generated screenplay: {screenplay_path}")
    console.print(f"Extracted characters: {len(analysis.characters)}")
    console.print(f"Extracted locations: {len(analysis.locations)}")
    console.print(f"Drafted scenes: {len(draft_result.drafted_scene_ids)}")
    console.print(f"Provider: {draft_result.provider}")
    console.print(f"Model: {draft_result.model}")

    if not schema.is_file():
        console.print(f"Validation skipped: schema file not found ({schema}).")
        return

    validation = validate_screenplay_file(screenplay_path, schema)
    if validation.passed:
        console.print(f"Validation passed: {screenplay_path}")
        return

    console.print(f"Validation failed: {len(validation.issues)} issue(s)")
    for issue in validation.issues:
        console.print(f"- {issue.code} {issue.path}: {issue.message}")
    raise typer.Exit(1)


@app.command("providers")
def providers_command() -> None:
    """List supported LLM providers and local configuration status."""

    for status in get_provider_statuses():
        configured = "configured" if status.configured else "missing config"
        console.print(f"{status.name}: {configured} ({status.detail})")


@app.command("check-provider")
def check_provider(
    provider: Annotated[
        str,
        typer.Option("--provider", help="Provider name to check."),
    ] = "mock",
    prompt: Annotated[
        str,
        typer.Option("--prompt", help="Prompt used for a small provider connectivity check."),
    ] = "请用一句话确认你可以帮助把小说改编成剧本。",
    max_tokens: Annotated[
        int,
        typer.Option("--max-tokens", min=1, help="Maximum tokens for the check response."),
    ] = 128,
) -> None:
    """Call a provider once to verify credentials and connectivity."""

    try:
        llm_provider = build_provider(provider)
        completion = llm_provider.complete(
            [ChatMessage(role="user", content=prompt)],
            max_tokens=max_tokens,
        )
    except ProviderError as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc

    console.print(f"Provider: {completion.provider}")
    console.print(f"Model: {completion.model}")
    console.print(f"Response: {completion.text}")


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


@app.command("draft-scenes")
def draft_scenes(
    workspace: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            readable=True,
            help="Workspace directory containing output/screenplay.yaml.",
        ),
    ] = Path("runs/demo"),
    provider: Annotated[
        str,
        typer.Option("--provider", help="Provider used to draft scene scripts."),
    ] = "mock",
    max_tokens: Annotated[
        int,
        typer.Option("--max-tokens", min=1, help="Maximum tokens per drafted scene."),
    ] = 2048,
    scene_limit: Annotated[
        int | None,
        typer.Option("--scene-limit", min=1, help="Draft only the first N scenes."),
    ] = None,
) -> None:
    """Draft screenplay scene scripts with an LLM provider."""

    layout = build_workspace_layout(workspace)
    screenplay_path = layout.output_dir / "screenplay.yaml"
    if not screenplay_path.is_file():
        console.print("No screenplay file found. Run novel2script generate first.")
        raise typer.Exit(1)

    try:
        document = load_yaml_document(screenplay_path)
        if not isinstance(document, dict):
            raise ProviderError("screenplay YAML must contain a top-level object.")
        llm_provider = build_provider(provider)
        result = draft_screenplay_scenes(
            document,
            llm_provider,
            max_tokens=max_tokens,
            scene_limit=scene_limit,
        )
    except ProviderError as exc:
        console.print(str(exc))
        raise typer.Exit(1) from exc

    write_screenplay_yaml(result.document, screenplay_path)
    console.print(f"Drafted scenes: {len(result.drafted_scene_ids)}")
    console.print(f"Provider: {result.provider}")
    console.print(f"Model: {result.model}")
    console.print(f"Wrote: {screenplay_path}")


@app.command()
def validate(
    workspace: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            readable=True,
            help="Workspace directory containing output/screenplay.yaml.",
        ),
    ] = Path("runs/demo"),
    schema: Annotated[
        Path,
        typer.Option(
            "--schema",
            help="Path to the screenplay JSON Schema file.",
        ),
    ] = Path("schemas/screenplay.schema.json"),
) -> None:
    """Validate output/screenplay.yaml against schema and ID references."""

    layout = build_workspace_layout(workspace)
    screenplay_path = layout.output_dir / "screenplay.yaml"
    if not screenplay_path.is_file():
        console.print("No screenplay file found. Run novel2script generate first.")
        raise typer.Exit(1)
    if not schema.is_file():
        console.print(f"No schema file found: {schema}")
        raise typer.Exit(1)

    result = validate_screenplay_file(screenplay_path, schema)
    if result.passed:
        console.print(f"Validation passed: {screenplay_path}")
        console.print(f"Schema: {schema}")
        return

    console.print(f"Validation failed: {len(result.issues)} issue(s)")
    for issue in result.issues:
        console.print(f"- {issue.code} {issue.path}: {issue.message}")
    raise typer.Exit(1)


@app.command()
def check(
    workspace: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            readable=True,
            help="Workspace directory containing output/screenplay.yaml.",
        ),
    ] = Path("runs/demo"),
    write: Annotated[
        bool,
        typer.Option(
            "--write/--no-write",
            help="Append findings to the screenplay quality_report (default: on).",
        ),
    ] = True,
) -> None:
    """Run story-level consistency checks and record findings in quality_report."""

    layout = build_workspace_layout(workspace)
    screenplay_path = layout.output_dir / "screenplay.yaml"
    if not screenplay_path.is_file():
        console.print("No screenplay file found. Run novel2script generate first.")
        raise typer.Exit(1)

    document = load_yaml_document(screenplay_path)
    if not isinstance(document, dict):
        console.print("screenplay YAML must contain a top-level object.")
        raise typer.Exit(1)

    findings = analyze_consistency(document)
    console.print(f"Consistency findings: {len(findings)}")
    for finding in findings:
        location = f" [{finding.scene_id}]" if finding.scene_id else ""
        console.print(f"- {finding.code}{location}: {finding.message}")

    if write and findings:
        apply_consistency_findings(document, findings)
        write_screenplay_yaml(document, screenplay_path)
        console.print(f"Wrote: {screenplay_path}")


def main() -> None:
    """Entrypoint used by the console script."""

    app()


if __name__ == "__main__":
    main()

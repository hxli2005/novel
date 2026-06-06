"""Command line interface for the novel-to-screenplay tool."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from novel_to_screenplay import __version__
from novel_to_screenplay.workspace import initialize_workspace, stage_source_file

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

    console.print("novel2script CLI skeleton is ready.")


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
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate inputs without writing output files."),
    ] = False,
) -> None:
    """Initialize a conversion run workspace.

    The real conversion pipeline will be implemented in later PRs. This command
    establishes the stable CLI contract and validates the input path.
    """

    input_path = _validate_input_path(input_path)

    if dry_run:
        console.print(
            f"Ready to run with provider '{provider}' using input '{input_path}'.",
        )
        return

    layout = initialize_workspace(out)
    staged_path = stage_source_file(input_path, layout)
    console.print(f"Initialized workspace: {layout.root}")
    console.print(f"Staged source: {staged_path}")
    console.print(f"Provider: {provider}")


def main() -> None:
    """Entrypoint used by the console script."""

    app()


if __name__ == "__main__":
    main()

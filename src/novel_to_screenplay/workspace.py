"""Workspace helpers for staged conversion runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from shutil import copyfile


@dataclass(frozen=True)
class WorkspaceLayout:
    """Filesystem layout for one conversion run."""

    root: Path
    input_dir: Path
    intermediates_dir: Path
    index_dir: Path


def build_workspace_layout(root: Path) -> WorkspaceLayout:
    """Return the standard workspace layout without touching the filesystem."""

    return WorkspaceLayout(
        root=root,
        input_dir=root / "input",
        intermediates_dir=root / "intermediates",
        index_dir=root / "index",
    )


def initialize_workspace(root: Path) -> WorkspaceLayout:
    """Create the standard workspace directories."""

    layout = build_workspace_layout(root)
    layout.input_dir.mkdir(parents=True, exist_ok=True)
    layout.intermediates_dir.mkdir(parents=True, exist_ok=True)
    layout.index_dir.mkdir(parents=True, exist_ok=True)
    return layout


def stage_source_file(source_path: Path, layout: WorkspaceLayout) -> Path:
    """Copy the user input file into the run workspace."""

    staged_path = layout.input_dir / f"source{source_path.suffix.lower()}"
    copyfile(source_path, staged_path)
    return staged_path

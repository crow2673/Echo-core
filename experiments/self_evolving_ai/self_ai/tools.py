from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ToolResult:
    name: str
    output: str
    success: bool


class ToolBox:
    """Small initial tool surface.

    More tools can be added by the AI's tool-builder in later versions.
    Dangerous actions remain outside the initial permission boundary.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()

    def list_files(self) -> ToolResult:
        items = sorted(str(p.relative_to(self.workspace)) for p in self.workspace.rglob("*") if p.is_file())
        return ToolResult("list_files", "\n".join(items), True)

    def run_test(self) -> ToolResult:
        result = subprocess.run(
            ["python", "-m", "pytest", "-q"],
            cwd=self.workspace,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return ToolResult("run_test", result.stdout + result.stderr, result.returncode == 0)

from __future__ import annotations

import ast
from pathlib import Path

from .safety import inspect_candidate


class ToolBuilder:
    """Build candidate Python tools behind a conservative static safety gate."""

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.tools_dir = self.workspace / "generated_tools"
        self.tools_dir.mkdir(parents=True, exist_ok=True)

    def create_candidate(self, name: str, source: str) -> Path:
        if not name.isidentifier():
            raise ValueError("Tool name must be a Python identifier.")

        tree = ast.parse(source)
        if not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in tree.body):
            raise ValueError("A generated tool must contain at least one function.")

        inspect_candidate(source)

        path = self.tools_dir / f"{name}.py"
        path.write_text(source, encoding="utf-8")

        compile(source, str(path), "exec")
        return path

    def list_candidates(self) -> list[str]:
        return sorted(p.name for p in self.tools_dir.glob("*.py"))

from __future__ import annotations

import ast

# The generated-tool gate is intentionally conservative. It rejects
# capabilities that would make static review meaningless.
BLOCKED_IMPORTS = {
    "subprocess",
    "socket",
    "requests",
    "urllib",
    "http",
    "ftplib",
    "telnetlib",
    "ctypes",
    "multiprocessing",
    "os",
    "sys",
    "pathlib",
    "shutil",
    "tempfile",
    "glob",
    "importlib",
}

BLOCKED_CALLS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "system",
    "popen",
    "remove",
    "unlink",
    "rmdir",
    "rmtree",
}


class CandidateRejected(ValueError):
    pass


def inspect_candidate(source: str) -> None:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise CandidateRejected(f"syntax error: {exc}") from exc

    if not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in tree.body):
        raise CandidateRejected("candidate must define at least one function")

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BLOCKED_IMPORTS:
                    raise CandidateRejected(f"blocked import: {root}")

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
                raise CandidateRejected(f"blocked call: {node.func.id}")
            if isinstance(node.func, ast.Attribute) and node.func.attr in BLOCKED_CALLS:
                raise CandidateRejected(f"blocked call: {node.func.attr}")

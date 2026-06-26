from __future__ import annotations

import ast
from pathlib import Path


def test_source_code_uses_logging_instead_of_print():
    offenders: list[str] = []
    for path in Path("src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                offenders.append(f"{path}:{node.lineno}")

    assert offenders == []

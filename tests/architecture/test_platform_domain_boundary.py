import ast
from pathlib import Path


def test_shared_platform_does_not_import_hospitality_or_infrastructure() -> None:
    platform_root = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "api"
        / "src"
        / "staylead_platform"
        / "platform"
    )
    forbidden = ("staylead_platform.domains", "staylead_platform.infrastructure")

    for source_file in platform_root.rglob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            else:
                continue
            assert not any(name.startswith(forbidden) for name in imported), source_file

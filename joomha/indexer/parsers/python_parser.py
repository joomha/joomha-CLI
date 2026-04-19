"""Python parser — extracts AST nodes and import edges using the stdlib `ast` module."""

import ast
from pathlib import Path
from typing import List, Dict, Optional

from joomha.indexer.parsers.base import BaseParser


class PythonParser(BaseParser):
    """Parse Python source files using the built-in `ast` module."""

    def extensions(self) -> List[str]:
        return [".py"]

    def language(self) -> str:
        return "python"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_import(module_name: str, repo_root: Path) -> Optional[str]:
        """Try to map a dotted module name to a relative file path."""
        parts = module_name.split(".")

        # package/__init__.py
        candidate = repo_root.joinpath(*parts, "__init__.py")
        if candidate.exists():
            return str(candidate.relative_to(repo_root))

        # module.py
        candidate = repo_root.joinpath(*parts).with_suffix(".py")
        if candidate.exists():
            return str(candidate.relative_to(repo_root))

        return None

    # ------------------------------------------------------------------
    # Interface implementation
    # ------------------------------------------------------------------

    def parse_file(
        self, file_path: Path, repo_root: Path
    ) -> Dict[str, List[Dict]]:
        """Parse one Python file and return nodes + edges."""
        rel_path = str(file_path.relative_to(repo_root))
        nodes: List[Dict] = []
        edges: List[Dict] = []

        try:
            source = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            return {"nodes": nodes, "edges": edges}

        # Module-level node
        line_count = len(source.splitlines())
        nodes.append({
            "file_path":  rel_path,
            "node_type":  "module",
            "name":       file_path.stem,
            "start_line": 1,
            "end_line":   line_count,
            "language":   "python",
        })

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nodes.append({
                    "file_path":  rel_path,
                    "node_type":  "function",
                    "name":       node.name,
                    "start_line": node.lineno,
                    "end_line":   node.end_lineno or node.lineno,
                    "language":   "python",
                })
            elif isinstance(node, ast.ClassDef):
                nodes.append({
                    "file_path":  rel_path,
                    "node_type":  "class",
                    "name":       node.name,
                    "start_line": node.lineno,
                    "end_line":   node.end_lineno or node.lineno,
                    "language":   "python",
                })
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    target = self._resolve_import(alias.name, repo_root)
                    if target:
                        edges.append({
                            "source_file": rel_path,
                            "target_file": target,
                            "edge_type":   "imports",
                        })
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    target = self._resolve_import(node.module, repo_root)
                    if target:
                        edges.append({
                            "source_file": rel_path,
                            "target_file": target,
                            "edge_type":   "imports",
                        })

        return {"nodes": nodes, "edges": edges}

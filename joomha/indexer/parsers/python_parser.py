"""Python parser — extracts AST nodes and import edges using the stdlib `ast` module.

Bug B fix: relative imports (from .utils import X) now resolve from the
source file's directory instead of always from the repo root.
"""

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
    def _resolve_import(
        module_name: str,
        repo_root: Path,
        source_file: Optional[Path] = None,
        level: int = 0,
    ) -> Optional[str]:
        """Try to map a dotted module name to a relative file path.

        Args:
            module_name: The dotted module string (e.g. "utils.helpers").
            repo_root:   Absolute path to the repo root.
            source_file: Absolute path to the file containing the import
                         (needed for relative imports).
            level:       Number of leading dots (0 = absolute, 1 = ., 2 = ..).
        """
        # --- Bug B: handle relative imports ---
        if level > 0 and source_file is not None:
            base_dir = source_file.parent
            # Walk up `level - 1` directories (level=1 means current package)
            for _ in range(level - 1):
                base_dir = base_dir.parent
        else:
            base_dir = repo_root

        parts = module_name.split(".") if module_name else []

        # package/__init__.py
        candidate = base_dir.joinpath(*parts, "__init__.py") if parts else None
        if candidate and candidate.exists():
            try:
                return str(candidate.relative_to(repo_root))
            except ValueError:
                pass

        # module.py
        if parts:
            candidate = base_dir.joinpath(*parts).with_suffix(".py")
            if candidate.exists():
                try:
                    return str(candidate.relative_to(repo_root))
                except ValueError:
                    pass

        # bare relative with no module name (e.g. `from . import foo`)
        if level > 0 and not module_name:
            candidate = base_dir / "__init__.py"
            if candidate.exists():
                try:
                    return str(candidate.relative_to(repo_root))
                except ValueError:
                    pass

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
                    target = self._resolve_import(
                        alias.name, repo_root, source_file=file_path, level=0
                    )
                    if target:
                        edges.append({
                            "source_file": rel_path,
                            "target_file": target,
                            "edge_type":   "imports",
                        })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                level = node.level or 0
                target = self._resolve_import(
                    module, repo_root, source_file=file_path, level=level
                )
                if target:
                    edges.append({
                        "source_file": rel_path,
                        "target_file": target,
                        "edge_type":   "imports",
                    })

        return {"nodes": nodes, "edges": edges}

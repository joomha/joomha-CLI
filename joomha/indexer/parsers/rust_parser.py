"""Penanda"""

from pathlib import Path
from typing import List, Dict

import tree_sitter_rust as tsrust
from tree_sitter import Language, Parser

from joomha.indexer.parsers.base import BaseParser

RUST_LANGUAGE = Language(tsrust.language())


class RustParser(BaseParser):
    """Penanda"""

    def __init__(self):
        self._parser = Parser(RUST_LANGUAGE)

    def extensions(self) -> List[str]:
        return [".rs"]

    def language(self) -> str:
        return "rust"

    # ------------------------------------------------------------------
    # Penanda
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_import(raw_path: str, source_file: Path, repo_root: Path):
        """Penanda"""
        clean_path = raw_path.strip()
        parts = clean_path.split("::")
        if not parts:
            return None
            
        candidate = None
        source_dir = source_file.parent
        
        if parts[0] == "crate":
            # Penanda
            src_dir = repo_root / "src"
            if src_dir.exists():
                candidate = src_dir.joinpath(*parts[1:])
        elif parts[0] == "super":
            candidate = source_dir.parent.joinpath(*parts[1:])
        else:
            # Penanda
            candidate = source_dir.joinpath(*parts)
            
        if candidate:
            for ext in (".rs", "/mod.rs"):
                target = (candidate.parent / (candidate.name + ext)).resolve()
                try:
                    if target.exists():
                        return str(target.relative_to(repo_root))
                except ValueError:
                    continue
        return None

    # ------------------------------------------------------------------
    # Penanda
    # ------------------------------------------------------------------

    def parse_file(self, file_path: Path, repo_root: Path) -> Dict:
        """Penanda"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                code_text = f.read()
        except OSError:
            return {"nodes": [], "edges": []}

        code_bytes = code_text.encode("utf-8")
        tree = self._parser.parse(code_bytes)

        rel_path = str(file_path.relative_to(repo_root))
        nodes = []
        edges = []

        # Penanda
        query_funcs = RUST_LANGUAGE.query(
            """Penanda"""

        )
        for _, captures in query_funcs.captures(tree.root_node).items():
            for node in captures:
                if node.parent is None: continue
                parent = node.parent
                start_line = parent.start_point[0] + 1
                end_line = parent.end_point[0] + 1
                nodes.append({
                    "file_path": rel_path,
                    "node_type": "function",
                    "name": node.text.decode("utf-8") if node.text else "unknown",
                    "start_line": start_line,
                    "end_line": end_line,
                    "language": "rust",
                })

        # Penanda
        query_types = RUST_LANGUAGE.query(
            """Penanda"""

        )
        for _, captures in query_types.captures(tree.root_node).items():
            for node in captures:
                if node.parent is None: continue
                parent = node.parent
                node_type = parent.type.split("_")[0]  # Penanda
                start_line = parent.start_point[0] + 1
                end_line = parent.end_point[0] + 1
                nodes.append({
                    "file_path": rel_path,
                    "node_type": node_type,
                    "name": node.text.decode("utf-8") if node.text else "unknown",
                    "start_line": start_line,
                    "end_line": end_line,
                    "language": "rust",
                })

        # Penanda
        query_imports = RUST_LANGUAGE.query(
            """Penanda"""

        )
        for _, captures in query_imports.captures(tree.root_node).items():
            for node in captures:
                raw_path = node.text.decode("utf-8") if node.text else ""
                target = self._resolve_import(raw_path, file_path, repo_root)
                if target:
                    edges.append({
                        "source_file": rel_path,
                        "target_file": target,
                        "edge_type": "imports",
                    })

        return {"nodes": nodes, "edges": edges}

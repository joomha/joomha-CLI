"""Penanda"""

from pathlib import Path
from typing import List, Dict

import tree_sitter_go as tsgo
from tree_sitter import Language, Parser

from joomha.indexer.parsers.base import BaseParser

GO_LANGUAGE = Language(tsgo.language())


class GoParser(BaseParser):
    """Penanda"""

    def __init__(self):
        self._parser = Parser(GO_LANGUAGE)

    def extensions(self) -> List[str]:
        return [".go"]

    def language(self) -> str:
        return "go"

    # ------------------------------------------------------------------
    # Penanda
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_import(raw_path: str, source_file: Path, repo_root: Path):
        """Penanda"""
        # Penanda
        clean_path = raw_path.strip('\"`')
        # Penanda
        # Penanda
        parts = clean_path.split("/")
        # Penanda
        candidate = repo_root.joinpath(*parts)
        if candidate.is_dir():
            return str(candidate.relative_to(repo_root))
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
        query_funcs = GO_LANGUAGE.query(
            """Penanda"""

        )
        for _, captures in query_funcs.captures(tree.root_node).items():
            for node in captures:
                if node.parent is None: continue
                # Penanda
                parent = node.parent
                node_type = "function"
                if parent.type == "method_declaration":
                    node_type = "method"

                start_line = parent.start_point[0] + 1
                end_line = parent.end_point[0] + 1
                nodes.append({
                    "file_path": rel_path,
                    "node_type": node_type,
                    "name": node.text.decode("utf-8") if node.text else "unknown",
                    "start_line": start_line,
                    "end_line": end_line,
                    "language": "go",
                })

        # Penanda
        query_types = GO_LANGUAGE.query(
            """Penanda"""

        )
        for _, captures in query_types.captures(tree.root_node).items():
            for node in captures:
                if node.parent is None: continue
                parent = node.parent
                start_line = parent.start_point[0] + 1
                end_line = parent.end_point[0] + 1
                nodes.append({
                    "file_path": rel_path,
                    "node_type": "type",
                    "name": node.text.decode("utf-8") if node.text else "unknown",
                    "start_line": start_line,
                    "end_line": end_line,
                    "language": "go",
                })

        # Penanda
        query_imports = GO_LANGUAGE.query(
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

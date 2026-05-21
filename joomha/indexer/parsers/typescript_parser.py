"""[PENANDA]"""

from pathlib import Path
from typing import List, Dict

import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

from joomha.indexer.parsers.base import BaseParser

TS_LANGUAGE = Language(tsts.language_typescript())
TSX_LANGUAGE = Language(tsts.language_tsx())


class TypeScriptParser(BaseParser):
    """Parser kode TypeScript dengan Tree-sitter"""

    def __init__(self):
        self._parser_ts = Parser(TS_LANGUAGE)
        self._parser_tsx = Parser(TSX_LANGUAGE)

    def extensions(self) -> List[str]:
        return [".ts", ".tsx"]

    def language(self) -> str:
        return "typescript"

    # ------------------------------------------------------------------
    # Fungsi Internal Pembantu
    # ------------------------------------------------------------------

    def _get_parser(self, file_path: Path) -> Parser:
        """Pilih sub-parser yang tepat"""
        if file_path.suffix == ".tsx":
            return self._parser_tsx
        return self._parser_ts

    @staticmethod
    def _resolve_import(raw_path: str, source_file: Path, repo_root: Path):
        """Selesaikan import relatif TypeScript"""
        if not raw_path.startswith("."):
            return None  # Lewati library eksternal (npm)

        source_dir = source_file.parent
        for ext in ("", ".ts", ".tsx", ".js", "/index.ts", "/index.tsx"):
            candidate = (source_dir / (raw_path + ext)).resolve()
            try:
                if candidate.exists():
                    return str(candidate.relative_to(repo_root))
            except ValueError:
                continue
        return None

    def _walk(self, node):
        """Generator Depth-first untuk node Tree-sitter"""
        yield node
        for child in node.children:
            yield from self._walk(child)

    # ------------------------------------------------------------------
    # Implementasi Antarmuka
    # ------------------------------------------------------------------

    def parse_file(
        self, file_path: Path, repo_root: Path
    ) -> Dict[str, List[Dict]]:
        rel_path = str(file_path.relative_to(repo_root))
        nodes: List[Dict] = []
        edges: List[Dict] = []

        try:
            source_bytes = file_path.read_bytes()
            source_text = source_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return {"nodes": nodes, "edges": edges}

        parser = self._get_parser(file_path)
        tree = parser.parse(source_bytes)
        line_count = len(source_text.splitlines())

        # Node level modul
        nodes.append({
            "file_path":  rel_path,
            "node_type":  "module",
            "name":       file_path.stem,
            "start_line": 1,
            "end_line":   line_count,
            "language":   "typescript",
        })

        for ts_node in self._walk(tree.root_node):
            ntype = ts_node.type

            # --- Functions ---
            if ntype in ("function_declaration", "generator_function_declaration"):
                name_node = ts_node.child_by_field_name("name")
                if name_node:
                    nodes.append({
                        "file_path":  rel_path,
                        "node_type":  "function",
                        "name":       name_node.text.decode(),
                        "start_line": ts_node.start_point[0] + 1,
                        "end_line":   ts_node.end_point[0] + 1,
                        "language":   "typescript",
                    })

            # --- Arrow / method assigned to variable ---
            elif ntype == "variable_declarator":
                value = ts_node.child_by_field_name("value")
                if value and value.type in (
                    "arrow_function", "function_expression",
                ):
                    name_node = ts_node.child_by_field_name("name")
                    if name_node:
                        nodes.append({
                            "file_path":  rel_path,
                            "node_type":  "function",
                            "name":       name_node.text.decode(),
                            "start_line": ts_node.start_point[0] + 1,
                            "end_line":   ts_node.end_point[0] + 1,
                            "language":   "typescript",
                        })

            # --- Classes ---
            elif ntype == "class_declaration":
                name_node = ts_node.child_by_field_name("name")
                if name_node:
                    nodes.append({
                        "file_path":  rel_path,
                        "node_type":  "class",
                        "name":       name_node.text.decode(),
                        "start_line": ts_node.start_point[0] + 1,
                        "end_line":   ts_node.end_point[0] + 1,
                        "language":   "typescript",
                    })

            # --- TypeScript Interfaces ---
            elif ntype == "interface_declaration":
                name_node = ts_node.child_by_field_name("name")
                if name_node:
                    nodes.append({
                        "file_path":  rel_path,
                        "node_type":  "interface",
                        "name":       name_node.text.decode(),
                        "start_line": ts_node.start_point[0] + 1,
                        "end_line":   ts_node.end_point[0] + 1,
                        "language":   "typescript",
                    })

            # --- TypeScript Type Aliases ---
            elif ntype == "type_alias_declaration":
                name_node = ts_node.child_by_field_name("name")
                if name_node:
                    nodes.append({
                        "file_path":  rel_path,
                        "node_type":  "type_alias",
                        "name":       name_node.text.decode(),
                        "start_line": ts_node.start_point[0] + 1,
                        "end_line":   ts_node.end_point[0] + 1,
                        "language":   "typescript",
                    })

            # --- Methods ---
            elif ntype == "method_definition":
                name_node = ts_node.child_by_field_name("name")
                if name_node:
                    nodes.append({
                        "file_path":  rel_path,
                        "node_type":  "function",
                        "name":       name_node.text.decode(),
                        "start_line": ts_node.start_point[0] + 1,
                        "end_line":   ts_node.end_point[0] + 1,
                        "language":   "typescript",
                    })

            # --- import ... from '...' ---
            elif ntype == "import_statement":
                source_node = ts_node.child_by_field_name("source")
                if source_node:
                    raw = source_node.text.decode().strip("'\"")
                    target = self._resolve_import(raw, file_path, repo_root)
                    if target:
                        edges.append({
                            "source_file": rel_path,
                            "target_file": target,
                            "edge_type":   "imports",
                        })

        return {"nodes": nodes, "edges": edges}

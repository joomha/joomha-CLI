"""[PENANDA]"""

from pathlib import Path
from typing import List, Dict

import tree_sitter_javascript as tsjs
from tree_sitter import Language, Parser

from joomha.indexer.parsers.base import BaseParser

JS_LANGUAGE = Language(tsjs.language())


class JavaScriptParser(BaseParser):
    """Parsing file JavaScript dengan Tree-sitter"""

    def __init__(self):
        self._parser = Parser(JS_LANGUAGE)

    def extensions(self) -> List[str]:
        return [".js", ".jsx", ".mjs", ".cjs"]

    def language(self) -> str:
        return "javascript"

    # ------------------------------------------------------------------
    # Fungsi Internal Pembantu
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_import(raw_path: str, source_file: Path, repo_root: Path):
        """Ubah path relatif menjadi statis"""
        if not raw_path.startswith("."):
            return None  # Lewati library eksternal (npm)

        source_dir = source_file.parent
        for ext in ("", ".js", ".jsx", ".mjs", ".ts", ".tsx", "/index.js", "/index.ts", "/index.tsx"):
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

        tree = self._parser.parse(source_bytes)
        line_count = len(source_text.splitlines())

        # Node level modul
        nodes.append({
            "file_path":  rel_path,
            "node_type":  "module",
            "name":       file_path.stem,
            "start_line": 1,
            "end_line":   line_count,
            "language":   "javascript",
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
                        "language":   "javascript",
                    })

            # --- Arrow / method assigned to variable ---
            elif ntype == "variable_declarator":
                value = ts_node.child_by_field_name("value")
                if value and value.type in ("arrow_function", "function_expression"):
                    name_node = ts_node.child_by_field_name("name")
                    if name_node:
                        nodes.append({
                            "file_path":  rel_path,
                            "node_type":  "function",
                            "name":       name_node.text.decode(),
                            "start_line": ts_node.start_point[0] + 1,
                            "end_line":   ts_node.end_point[0] + 1,
                            "language":   "javascript",
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
                        "language":   "javascript",
                    })

            # --- Methods inside classes ---
            elif ntype == "method_definition":
                name_node = ts_node.child_by_field_name("name")
                if name_node:
                    nodes.append({
                        "file_path":  rel_path,
                        "node_type":  "function",
                        "name":       name_node.text.decode(),
                        "start_line": ts_node.start_point[0] + 1,
                        "end_line":   ts_node.end_point[0] + 1,
                        "language":   "javascript",
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

            # --- require('...') ---
            elif ntype == "call_expression":
                func = ts_node.child_by_field_name("function")
                if func and func.text == b"require":
                    args = ts_node.child_by_field_name("arguments")
                    if args and args.named_child_count > 0:
                        arg = args.named_children[0]
                        if arg.type == "string":
                            raw = arg.text.decode().strip("'\"")
                            target = self._resolve_import(
                                raw, file_path, repo_root
                            )
                            if target:
                                edges.append({
                                    "source_file": rel_path,
                                    "target_file": target,
                                    "edge_type":   "imports",
                                })

        return {"nodes": nodes, "edges": edges}

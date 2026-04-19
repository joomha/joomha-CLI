"""Graph-based retriever — relational traversal via SQLite (nodes + edges + co-changes)."""

import re
import sqlite3
from pathlib import Path
from typing import List, Dict, Set


class GraphRetriever:
    """Retrieve code context through structural & co-change relationships."""

    def __init__(self, db_path: str, repo_root: str):
        self.db_path = db_path
        self.repo_root = Path(repo_root)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _extract_keywords(self, query: str) -> List[str]:
        """Extract CamelCase, snake_case tokens, and long words from the query."""
        pattern = r'\b[A-Z][a-zA-Z]+\b|[a-z]+_[a-z_]+\b'
        keywords = re.findall(pattern, query)
        # Fallback: any word longer than 4 characters
        if not keywords:
            words = re.findall(r'\b\w+\b', query)
            keywords = [w for w in words if len(w) > 4]
        return list(set(keywords))

    def _find_nodes(self, keywords: List[str]) -> List[Dict]:
        """Find AST nodes whose name matches any keyword."""
        conn = self._get_conn()
        cursor = conn.cursor()
        nodes: List[Dict] = []
        seen: Set[tuple] = set()

        for kw in keywords:
            cursor.execute(
                "SELECT file_path, node_type, name, start_line, end_line "
                "FROM nodes WHERE name LIKE ?",
                (f"%{kw}%",),
            )
            for row in cursor.fetchall():
                key = (row[0], row[2])
                if key not in seen:
                    seen.add(key)
                    nodes.append({
                        "file_path":  row[0],
                        "node_type":  row[1],
                        "name":       row[2],
                        "start_line": row[3],
                        "end_line":   row[4],
                    })

        conn.close()
        return nodes

    def _get_import_neighbors(self, file_path: str) -> List[str]:
        """Get files that import *or are imported by* the given file."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT source_file FROM edges "
            "WHERE target_file LIKE ? AND edge_type='imports'",
            (f"%{file_path}%",),
        )
        results = [row[0] for row in cursor.fetchall()]

        cursor.execute(
            "SELECT target_file FROM edges "
            "WHERE source_file LIKE ? AND edge_type='imports'",
            (f"%{file_path}%",),
        )
        results.extend(row[0] for row in cursor.fetchall())

        conn.close()
        return list(set(results))

    def _get_cochange_neighbors(self, file_path: str) -> List[Dict]:
        """Get files that frequently change alongside the given file."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT file_b, score FROM co_changes WHERE file_a LIKE ? "
            "UNION "
            "SELECT file_a, score FROM co_changes WHERE file_b LIKE ?",
            (f"%{file_path}%", f"%{file_path}%"),
        )
        results = [{"file": row[0], "score": row[1]} for row in cursor.fetchall()]
        conn.close()
        return sorted(results, key=lambda x: x["score"], reverse=True)

    def _read_file_content(self, file_path: str, max_chars: int = 3000) -> str:
        """Read the first *max_chars* of a file from the repo."""
        full_path = self.repo_root / file_path
        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
            return content[:max_chars]
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(self, query: str) -> List[Dict]:
        """Retrieve context by graph traversal.

        Returns an empty list when no nodes match — the Orchestrator will
        automatically fall back to the VectorRetriever.
        """
        keywords = self._extract_keywords(query)
        if not keywords:
            return []

        nodes = self._find_nodes(keywords)
        if not nodes:
            return []

        # Take the top 3 most relevant nodes
        top_nodes = nodes[:3]
        results: List[Dict] = []
        seen_files: Set[str] = set()

        for node in top_nodes:
            fp = node["file_path"]
            if fp in seen_files:
                continue
            seen_files.add(fp)

            content = self._read_file_content(fp)
            importers = self._get_import_neighbors(fp)
            cochanges = self._get_cochange_neighbors(fp)

            results.append({
                "file_path":  fp,
                "text":       content,
                "node_type":  node["node_type"],
                "node_name":  node["name"],
                "start_line": node["start_line"],
                "end_line":   node["end_line"],
                "importers":  importers[:5],
                "cochanges":  cochanges[:5],
                "source":     "graph",
            })

        return results

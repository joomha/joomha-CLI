"""Tests for AST parser."""

import sqlite3
import tempfile
from pathlib import Path

from joomha.indexer.ast_parser import init_db, parse_file, parse_repo


def test_init_db_creates_all_tables():
    """init_db should create all 7 tables."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = sorted(row[0] for row in cursor.fetchall())
    conn.close()

    expected = sorted([
        "co_changes", "commits", "edges", "file_changes",
        "hotspots", "nodes", "ownership",
    ])
    assert tables == expected, f"Expected {expected}, got {tables}"


def test_parse_file_extracts_nodes():
    """parse_file should extract functions and classes as nodes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        py_file = repo / "sample.py"
        py_file.write_text(
            'class Foo:\n    def bar(self):\n        pass\n\ndef baz():\n    pass\n',
            encoding="utf-8",
        )

        db_path = str(repo / "test.db")
        conn = init_db(db_path)
        parse_file(py_file, repo, conn)

        cursor = conn.cursor()
        cursor.execute("SELECT node_type, name FROM nodes ORDER BY name")
        rows = cursor.fetchall()
        conn.close()

        names = {row[1] for row in rows}
        assert "Foo" in names, "Should find class Foo"
        assert "bar" in names, "Should find method bar"
        assert "baz" in names, "Should find function baz"
        assert "sample" in names, "Should find module node"

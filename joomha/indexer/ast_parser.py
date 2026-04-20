"""AST parser — extracts code structure (functions, classes, imports) into SQLite.

Now supports multiple languages via the pluggable parser system in
joomha.indexer.parsers. Each language parser implements BaseParser and is
auto-registered by file extension.
"""

import sqlite3
from pathlib import Path
from typing import Optional, List

EXCLUDE_DIRS = {".venv", ".git", "__pycache__", "node_modules", ".joomha"}

# ---------------------------------------------------------------------------
# Supported file extensions (union of all registered parsers)
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}

# ---------------------------------------------------------------------------
# Database initialisation (creates ALL 7 tables used by the whole system)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path  TEXT NOT NULL,
    node_type  TEXT NOT NULL,
    name       TEXT NOT NULL,
    start_line INTEGER,
    end_line   INTEGER,
    language   TEXT DEFAULT 'python'
);

CREATE TABLE IF NOT EXISTS edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    target_file TEXT NOT NULL,
    edge_type   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commits (
    hash    TEXT PRIMARY KEY,
    author  TEXT,
    date    TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS file_changes (
    commit_hash TEXT,
    file_path   TEXT,
    FOREIGN KEY (commit_hash) REFERENCES commits(hash)
);

CREATE TABLE IF NOT EXISTS co_changes (
    file_a TEXT NOT NULL,
    file_b TEXT NOT NULL,
    score  INTEGER DEFAULT 1,
    PRIMARY KEY (file_a, file_b)
);

CREATE TABLE IF NOT EXISTS hotspots (
    file_path    TEXT PRIMARY KEY,
    change_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ownership (
    file_path TEXT NOT NULL,
    author    TEXT NOT NULL,
    changes   INTEGER DEFAULT 1,
    PRIMARY KEY (file_path, author)
);

-- Bug D: indexes to avoid full table scans in retriever queries
CREATE INDEX IF NOT EXISTS ix_nodes_name      ON nodes (name);
CREATE INDEX IF NOT EXISTS ix_nodes_file_path ON nodes (file_path);
CREATE INDEX IF NOT EXISTS ix_edges_source    ON edges (source_file);
CREATE INDEX IF NOT EXISTS ix_edges_target    ON edges (target_file);
CREATE INDEX IF NOT EXISTS ix_cochanges_a     ON co_changes (file_a);
CREATE INDEX IF NOT EXISTS ix_cochanges_b     ON co_changes (file_b);
CREATE INDEX IF NOT EXISTS ix_file_changes_fp ON file_changes (file_path);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """Create (or open) the SQLite database with all required tables."""
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA_SQL)

    # Migration: add `language` column if missing (upgrades old databases)
    cursor = conn.execute("PRAGMA table_info(nodes)")
    columns = {row[1] for row in cursor.fetchall()}
    if "language" not in columns:
        conn.execute("ALTER TABLE nodes ADD COLUMN language TEXT DEFAULT 'python'")

    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Parser registry
# ---------------------------------------------------------------------------

def _build_parser_registry():
    """Lazily build a dict mapping file extension → parser instance."""
    from joomha.indexer.parsers.python_parser import PythonParser
    from joomha.indexer.parsers.javascript_parser import JavaScriptParser
    from joomha.indexer.parsers.typescript_parser import TypeScriptParser

    registry = {}
    for parser_cls in (PythonParser, JavaScriptParser, TypeScriptParser):
        instance = parser_cls()
        for ext in instance.extensions():
            registry[ext] = instance
    return registry


_PARSER_REGISTRY = None  # lazy singleton


def _get_registry():
    global _PARSER_REGISTRY
    if _PARSER_REGISTRY is None:
        _PARSER_REGISTRY = _build_parser_registry()
    return _PARSER_REGISTRY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _should_exclude(rel_path: Path) -> bool:
    """Return True if the path contains an excluded directory."""
    return any(part in EXCLUDE_DIRS for part in rel_path.parts)


def _resolve_import(module_name: str, repo_root: Path) -> Optional[str]:
    """Try to map a dotted module name to a relative file path in the repo."""
    parts = module_name.split(".")

    # package/__init__.py
    candidate = repo_root.joinpath(*parts, "__init__.py")
    if candidate.exists():
        return str(candidate.relative_to(repo_root))

    # module.py (with parent package)
    candidate = repo_root.joinpath(*parts).with_suffix(".py")
    if candidate.exists():
        return str(candidate.relative_to(repo_root))

    return None


# ---------------------------------------------------------------------------
# Single-file parser (now dispatches to the correct language parser)
# ---------------------------------------------------------------------------

def parse_file(file_path: Path, repo_root: Path, conn: sqlite3.Connection) -> None:
    """Parse one source file and insert nodes/edges into the database.

    Dispatches to the appropriate language parser based on file extension.
    Silently skips files with unsupported extensions.
    """
    registry = _get_registry()
    parser = registry.get(file_path.suffix.lower())
    if parser is None:
        return  # unsupported extension

    result = parser.parse_file(file_path, repo_root)

    cursor = conn.cursor()

    for node in result.get("nodes", []):
        cursor.execute(
            "INSERT INTO nodes (file_path, node_type, name, start_line, end_line, language) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                node["file_path"],
                node["node_type"],
                node["name"],
                node["start_line"],
                node["end_line"],
                node.get("language", parser.language()),
            ),
        )

    for edge in result.get("edges", []):
        cursor.execute(
            "INSERT INTO edges (source_file, target_file, edge_type) "
            "VALUES (?, ?, ?)",
            (edge["source_file"], edge["target_file"], edge["edge_type"]),
        )

    conn.commit()


# ---------------------------------------------------------------------------
# Repo-wide parser
# ---------------------------------------------------------------------------

def parse_repo(repo_root: Path, conn: sqlite3.Connection, progress_callback=None) -> int:
    """Parse every supported source file in the repo.

    Scans for: .py, .js, .jsx, .mjs, .cjs, .ts, .tsx
    Returns the number of files parsed.
    """
    source_files = [
        f for f in repo_root.rglob("*")
        if f.suffix.lower() in SUPPORTED_EXTENSIONS
        and not _should_exclude(f.relative_to(repo_root))
    ]

    total = len(source_files)
    if progress_callback:
        progress_callback(0, total)

    count = 0
    for src_file in source_files:
        parse_file(src_file, repo_root, conn)
        count += 1
        if progress_callback:
            progress_callback(count, total)

    return count

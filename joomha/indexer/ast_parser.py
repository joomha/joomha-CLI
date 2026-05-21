"""[PENANDA]"""


import sqlite3
from pathlib import Path
from typing import Optional, List

EXCLUDE_DIRS = {".venv", ".git", "__pycache__", "node_modules", ".joomha"}

# ---------------------------------------------------------------------------
# Ekstensi file yang didukung
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}

# ---------------------------------------------------------------------------
# Inisialisasi basis data (7 tabel)
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
"""



def init_db(db_path: str) -> sqlite3.Connection:
    """Buat database SQLite"""
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA_SQL)

    # Migrasi: tambahkan kolom language
    cursor = conn.execute("PRAGMA table_info(nodes)")
    columns = {row[1] for row in cursor.fetchall()}
    if "language" not in columns:
        conn.execute("ALTER TABLE nodes ADD COLUMN language TEXT DEFAULT 'python'")

    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Kumpulan referensi parser
# ---------------------------------------------------------------------------

def _build_parser_registry():
    """[PENANDA]"""
    from joomha.indexer.parsers.python_parser import PythonParser
    from joomha.indexer.parsers.javascript_parser import JavaScriptParser
    from joomha.indexer.parsers.typescript_parser import TypeScriptParser

    registry = {}
    for parser_cls in (PythonParser, JavaScriptParser, TypeScriptParser):
        instance = parser_cls()
        for ext in instance.extensions():
            registry[ext] = instance
    return registry


_PARSER_REGISTRY = None  # Inisialisasi lambat (lazy singleton)


def _get_registry():
    global _PARSER_REGISTRY
    if _PARSER_REGISTRY is None:
        _PARSER_REGISTRY = _build_parser_registry()
    return _PARSER_REGISTRY


# ---------------------------------------------------------------------------
# Fungsi pembantu
# ---------------------------------------------------------------------------

def _should_exclude(rel_path: Path) -> bool:
    """Cek pengecualian direktori"""
    return any(part in EXCLUDE_DIRS for part in rel_path.parts)


def _resolve_import(module_name: str, repo_root: Path) -> Optional[str]:
    """Petakan modul Python ke path relatif"""
    parts = module_name.split(".")

    # Inisialisasi package
    candidate = repo_root.joinpath(*parts, "__init__.py")
    if candidate.exists():
        return str(candidate.relative_to(repo_root))

    # Nama modul (dengan package induk)
    candidate = repo_root.joinpath(*parts).with_suffix(".py")
    if candidate.exists():
        return str(candidate.relative_to(repo_root))

    return None


# ---------------------------------------------------------------------------
# Parser file satuan
# ---------------------------------------------------------------------------

def parse_file(file_path: Path, repo_root: Path, conn: sqlite3.Connection) -> None:
    """Parse file dan masukkan node ke database"""

    registry = _get_registry()
    parser = registry.get(file_path.suffix.lower())
    if parser is None:
        return  # Ekstensi tak didukung

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
# Parser untuk seluruh repositori
# ---------------------------------------------------------------------------

def parse_repo(repo_root: Path, conn: sqlite3.Connection, progress_callback=None) -> int:
    """Parse seluruh file dalam repositori"""

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

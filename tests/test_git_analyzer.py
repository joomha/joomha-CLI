"""Tests for Git analyzer."""

import sqlite3
import tempfile
from pathlib import Path

from joomha.indexer.ast_parser import init_db


def test_git_analyzer_handles_non_git_repo():
    """analyze_git should return 0 for non-git directories."""
    from joomha.indexer.git_analyzer import analyze_git

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        db_path = str(repo / "test.db")
        conn = init_db(db_path)

        count = analyze_git(repo, conn)
        conn.close()

        assert count == 0, "Should return 0 for non-git repo"

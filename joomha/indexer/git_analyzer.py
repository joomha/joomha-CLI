"""Git history analyser — commits, co-changes, hotspots, and ownership."""

import sqlite3
from itertools import combinations
from pathlib import Path

import git


def analyze_git(repo_path: Path, conn: sqlite3.Connection, progress_callback=None) -> int:
    """Analyse the full git history and populate SQLite tables.

    Returns the number of commits processed.
    """
    try:
        repo = git.Repo(str(repo_path))
    except git.InvalidGitRepositoryError:
        return 0

    cursor = conn.cursor()
    commit_count = 0

    commits = list(repo.iter_commits())
    total = len(commits)
    if progress_callback:
        progress_callback(0, total)

    for commit in commits:
        cursor.execute(
            "INSERT OR IGNORE INTO commits (hash, author, date, message) "
            "VALUES (?, ?, ?, ?)",
            (
                commit.hexsha,
                str(commit.author),
                commit.committed_datetime.isoformat(),
                commit.message.strip(),
            ),
        )

        # Collect changed Python files in this commit
        changed_files: list[str] = []
        try:
            if commit.parents:
                diffs = commit.diff(commit.parents[0])
            else:
                diffs = commit.diff(git.NULL_TREE)

            for diff in diffs:
                fp = diff.a_path or diff.b_path
                if fp and fp.endswith(".py"):
                    changed_files.append(fp)
                    cursor.execute(
                        "INSERT INTO file_changes (commit_hash, file_path) "
                        "VALUES (?, ?)",
                        (commit.hexsha, fp),
                    )
        except Exception:
            # Skip problematic commits (e.g. binary-only)
            continue

        # Co-changes: every *sorted* pair of files in this commit
        for a, b in combinations(sorted(set(changed_files)), 2):
            cursor.execute(
                "INSERT INTO co_changes (file_a, file_b, score) VALUES (?, ?, 1) "
                "ON CONFLICT(file_a, file_b) DO UPDATE SET score = score + 1",
                (a, b),
            )

        commit_count += 1
        if progress_callback:
            progress_callback(commit_count, total)

    # ---------------------------------------------------------------------------
    # Aggregate tables
    # ---------------------------------------------------------------------------

    # Hotspots: how often each file was changed
    cursor.execute("""
        INSERT OR REPLACE INTO hotspots (file_path, change_count)
        SELECT file_path, COUNT(*) AS cnt
        FROM file_changes
        GROUP BY file_path
    """)

    # Ownership: per-file author contribution
    cursor.execute("""
        INSERT OR REPLACE INTO ownership (file_path, author, changes)
        SELECT fc.file_path, c.author, COUNT(*) AS cnt
        FROM file_changes fc
        JOIN commits c ON fc.commit_hash = c.hash
        GROUP BY fc.file_path, c.author
    """)

    conn.commit()
    return commit_count

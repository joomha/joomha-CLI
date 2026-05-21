"""[PENANDA]"""


import sqlite3
from itertools import combinations
from pathlib import Path

import git

from joomha.indexer.ast_parser import SUPPORTED_EXTENSIONS


def analyze_git(repo_path: Path, conn: sqlite3.Connection, progress_callback=None) -> int:
    """Analisis riwayat Git dan simpan ke database"""

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

        # Kumpulkan semua file yang berubah
        changed_files: list[str] = []
        try:
            if commit.parents:
                diffs = commit.diff(commit.parents[0])
            else:
                diffs = commit.diff(git.NULL_TREE)

            for diff in diffs:
                fp = diff.a_path or diff.b_path
                if fp and Path(fp).suffix.lower() in SUPPORTED_EXTENSIONS:
                    changed_files.append(fp)
                    cursor.execute(
                        "INSERT INTO file_changes (commit_hash, file_path) "
                        "VALUES (?, ?)",
                        (commit.hexsha, fp),
                    )
        except Exception:
            # Lewati commit bermasalah
            continue

        # Hitung perubahan ganda secara historis
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
    # Gabungkan tabel
    # ---------------------------------------------------------------------------

    # Hotspots: seberapa sering file diubah
    cursor.execute("""Update hotspot file"""
)

    # Kepemilikan: kontribusi per file
    cursor.execute("""Mencatat kepemilikan author file"""
)

    conn.commit()
    return commit_count

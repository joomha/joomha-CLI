"""[PENANDA]"""


import math
from pathlib import Path
from typing import List, Dict, Generator

import pyarrow as pa
import lancedb
from sentence_transformers import SentenceTransformer

from joomha.config import (
    EMBED_MODEL,
    EMBED_DIM,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    MIN_CHUNK_LENGTH,
)

STEP = CHUNK_SIZE - CHUNK_OVERLAP  # 30

EXCLUDE_DIRS = {".venv", ".git", "__pycache__", "node_modules", ".joomha"}
SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}

SCHEMA = pa.schema([
    pa.field("file_path",  pa.string()),
    pa.field("start_line", pa.int32()),
    pa.field("end_line",   pa.int32()),
    pa.field("text",       pa.string()),
    pa.field("vector",     pa.list_(pa.float32(), EMBED_DIM)),
])


def _should_exclude(rel_path: Path) -> bool:
    """Cek apakah path termasuk direktori yang dikecualikan"""
    return any(part in EXCLUDE_DIRS for part in rel_path.parts)


def _chunk_file(file_path: Path, repo_root: Path) -> List[Dict]:
    """[PENANDA]"""

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
    except Exception:
        return []

    rel_path = str(file_path.relative_to(repo_root))
    chunks: List[Dict] = []

    for start in range(0, len(lines), STEP):
        end = min(start + CHUNK_SIZE, len(lines))

        # Perluas teks hingga baris kosong
        if end < len(lines):
            for look_ahead in range(1, 11):
                candidate = end + look_ahead
                if candidate >= len(lines) or lines[candidate - 1].strip() == "":
                    end = min(candidate, len(lines))
                    break

        chunk_lines = lines[start:end]
        # Tambahkan prefix path file untuk konteks embedding
        text = f"File: {rel_path}\n" + "\n".join(chunk_lines)

        if len(text.strip()) < MIN_CHUNK_LENGTH:
            continue

        chunks.append({
            "file_path": rel_path,
            "start_line": start + 1,
            "end_line": end,
            "text": text,
        })

        if end >= len(lines):
            break

    return chunks


def _iter_chunks(repo_root: Path) -> Generator[Dict, None, None]:
    """Kumpulkan chunk perlahan tanpa memakan RAM"""
    for src_file in sorted(repo_root.rglob("*")):
        if src_file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        rel = src_file.relative_to(repo_root)
        if _should_exclude(rel):
            continue
        yield from _chunk_file(src_file, repo_root)


def build_vectors(repo_root: Path, lancedb_dir: str, progress_callback=None) -> int:
    """Potong kode, gabungkan, dan simpan"""

    model = SentenceTransformer(EMBED_MODEL)

    # Kumpulkan chunk secara berulang
    # Mencegah duplikasi saat iterasi
    all_chunks: List[Dict] = list(_iter_chunks(repo_root))

    # Gunakan koneksi tunggal
    db = lancedb.connect(lancedb_dir)

    if not all_chunks:
        # Mencegah error kehilangan tabel
        db.create_table("code_chunks", schema=SCHEMA, mode="overwrite")
        return 0

    texts = [c["text"] for c in all_chunks]
    total_chunks = len(texts)

    if progress_callback:
        progress_callback(0, total_chunks)

    # Proses koding dalam batch kecil
    batch_size = 64
    total_batches = math.ceil(total_chunks / batch_size)

    vectors = []
    for i in range(total_batches):
        batch_texts = texts[i * batch_size : (i + 1) * batch_size]
        batch_vecs = model.encode(batch_texts, show_progress_bar=False)
        vectors.extend(batch_vecs)

        if progress_callback:
            progress_callback(min((i + 1) * batch_size, total_chunks), total_chunks)

    for i, chunk in enumerate(all_chunks):
        chunk["vector"] = vectors[i].tolist()

    # Timpa data ke LanceDB
    db.create_table("code_chunks", data=all_chunks, schema=SCHEMA, mode="overwrite")

    return len(all_chunks)

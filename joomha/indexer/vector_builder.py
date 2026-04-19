"""Vector embedding builder — chunks source files and stores in LanceDB.

Supports Python, JavaScript, and TypeScript files.
"""

from pathlib import Path
from typing import List, Dict

import pyarrow as pa
import lancedb
from sentence_transformers import SentenceTransformer

CHUNK_SIZE = 40
OVERLAP = 10
STEP = CHUNK_SIZE - OVERLAP  # 30
MIN_CHUNK_LENGTH = 30
EMBED_MODEL = "all-MiniLM-L6-v2"
EMBED_DIM = 384

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
    """Return True if path contains an excluded directory."""
    return any(part in EXCLUDE_DIRS for part in rel_path.parts)


def _chunk_file(file_path: Path, repo_root: Path) -> List[Dict]:
    """Split a file into overlapping chunks of CHUNK_SIZE lines."""
    try:
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []

    rel_path = str(file_path.relative_to(repo_root))
    chunks: List[Dict] = []

    for start in range(0, len(lines), STEP):
        end = min(start + CHUNK_SIZE, len(lines))
        text = "\n".join(lines[start:end])

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


def build_vectors(repo_root: Path, lancedb_dir: str, progress_callback=None) -> int:
    """Chunk all supported source files, embed them, and store in LanceDB.

    Returns the number of chunks created.
    """
    model = SentenceTransformer(EMBED_MODEL)

    all_chunks: List[Dict] = []
    for src_file in sorted(repo_root.rglob("*")):
        if src_file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        rel = src_file.relative_to(repo_root)
        if _should_exclude(rel):
            continue
        all_chunks.extend(_chunk_file(src_file, repo_root))

    db = lancedb.connect(lancedb_dir)
    
    if not all_chunks:
        # Create empty table to prevent Missing Table errors
        db.create_table("code_chunks", schema=SCHEMA, mode="overwrite")
        return 0

    texts = [c["text"] for c in all_chunks]
    total_chunks = len(texts)
    
    if progress_callback:
        progress_callback(0, total_chunks)
        
    import math
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

    # Write to LanceDB (overwrite for clean re-index)
    db = lancedb.connect(lancedb_dir)
    db.create_table("code_chunks", data=all_chunks, schema=SCHEMA, mode="overwrite")

    return len(all_chunks)

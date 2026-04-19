"""Tests for vector builder and retriever."""


def test_chunk_file_produces_chunks():
    """_chunk_file should split a file into overlapping chunks."""
    import tempfile
    from pathlib import Path
    from joomha.indexer.vector_builder import _chunk_file

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        py_file = repo / "big.py"
        # Create a file with 100 lines
        lines = [f"line_{i} = {i}" for i in range(100)]
        py_file.write_text("\n".join(lines), encoding="utf-8")

        chunks = _chunk_file(py_file, repo)

        assert len(chunks) > 0, "Should produce at least one chunk"
        assert chunks[0]["file_path"] == "big.py"
        assert chunks[0]["start_line"] == 1
        assert chunks[0]["end_line"] == 40  # CHUNK_SIZE = 40

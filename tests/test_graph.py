"""Tests for graph retriever."""


def test_extract_keywords():
    """_extract_keywords should find CamelCase and snake_case tokens."""
    from joomha.retriever.graph import GraphRetriever

    # We only need the method, not a real DB
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        retriever = GraphRetriever(
            db_path=str(Path(tmpdir) / "dummy.db"),
            repo_root=tmpdir,
        )

        kw = retriever._extract_keywords("How does AuthHandler work?")
        assert "AuthHandler" in kw, "Should find CamelCase token"

        kw2 = retriever._extract_keywords("explain user_manager logic")
        assert "user_manager" in kw2, "Should find snake_case token"

        kw3 = retriever._extract_keywords("what is x?")
        # Fallback: no camel/snake found, should find words > 4 chars
        assert len(kw3) == 0 or all(len(w) > 4 for w in kw3)

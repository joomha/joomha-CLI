"""Orchestrator — the brain that wires retriever → prompt → LLM → logging."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Tuple

from joomha.retriever.vector import VectorRetriever
from joomha.retriever.graph import GraphRetriever
from joomha.llm.client import LLMClient
from joomha.llm.prompt_builder import build_prompt


class Orchestrator:
    """Central coordinator for the Joomha Q&A pipeline."""

    def __init__(self, repo_root: str, db_path: str, lancedb_dir: str):
        self.repo_root = repo_root
        self.db_path = db_path
        self.lancedb_dir = lancedb_dir
        self.joomha_dir = Path(repo_root) / ".joomha"
        self.session_log_path = self.joomha_dir / "session_log.json"

        self.current_mode = "graph"  # default mode

        # Initialise components
        self.vector_retriever = VectorRetriever(lancedb_dir)
        self.graph_retriever = GraphRetriever(db_path, repo_root)
        self.llm_client = LLMClient()

    # ------------------------------------------------------------------
    # Mode management
    # ------------------------------------------------------------------

    def set_mode(self, mode: str) -> str:
        """Switch retrieval mode. Returns a status message."""
        if mode in ("vector", "graph", "compare"):
            self.current_mode = mode
            return f"Mode diubah ke: {mode}"
        return f"Mode tidak valid: {mode}. Gunakan: vector, graph, compare"

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_interaction(self, query: str, result: Dict) -> None:
        """Append this Q&A turn to session_log.json."""
        log_entry = {
            "query": query,
            "mode": result.get("mode_used", ""),
            "answer": result.get("answer", "")[:500],
            "latency": result.get("latency", 0),
            "context_count": result.get("context_count", 0),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        logs: list = []
        if self.session_log_path.exists():
            try:
                logs = json.loads(
                    self.session_log_path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError):
                logs = []

        logs.append(log_entry)
        self.session_log_path.write_text(
            json.dumps(logs, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def ask(self, query: str) -> Dict:
        """Run the full RAG pipeline for a user question."""
        if self.current_mode == "compare":
            return self._ask_compare(query)
        if self.current_mode == "vector":
            return self._ask_single(query, "vector")
        # default: graph with automatic fallback
        return self._ask_single(query, "graph")

    def _ask_single(self, query: str, mode: str) -> Dict:
        """Execute a single-mode query (vector or graph w/ fallback)."""
        mode_used = mode

        if mode == "graph":
            context = self.graph_retriever.retrieve(query)
            if not context:
                # Automatic fallback — this is a feature, not an error.
                context = self.vector_retriever.retrieve(query)
                mode_used = "vector (fallback)"
        else:
            context = self.vector_retriever.retrieve(query)

        prompt = build_prompt(query, context, mode_used)
        answer, latency = self.llm_client.generate(prompt)

        result = {
            "answer": answer,
            "mode_used": mode_used,
            "latency": latency,
            "context_count": len(context),
        }
        self._log_interaction(query, result)
        return result

    def _ask_compare(self, query: str) -> Dict:
        """Run both retrievers side-by-side and return combined answer."""
        # --- Vector ---
        v_context = self.vector_retriever.retrieve(query)
        v_prompt = build_prompt(query, v_context, "vector")
        v_answer, v_latency = self.llm_client.generate(v_prompt)

        # --- Graph (with fallback) ---
        g_context = self.graph_retriever.retrieve(query)
        g_mode = "graph"
        if not g_context:
            g_context = self.vector_retriever.retrieve(query)
            g_mode = "vector (fallback)"
        g_prompt = build_prompt(query, g_context, g_mode)
        g_answer, g_latency = self.llm_client.generate(g_prompt)

        combined_answer = (
            f"## 🔵 Vector Retrieval\n{v_answer}\n\n"
            f"---\n\n"
            f"## 🟢 Graph Retrieval ({g_mode})\n{g_answer}"
        )

        result = {
            "answer": combined_answer,
            "mode_used": "compare",
            "latency": v_latency + g_latency,
            "context_count": len(v_context) + len(g_context),
            "vector_answer": v_answer,
            "graph_answer": g_answer,
            "vector_latency": v_latency,
            "graph_latency": g_latency,
        }
        self._log_interaction(query, result)
        return result

    # ------------------------------------------------------------------
    # Utility queries
    # ------------------------------------------------------------------

    def get_hotspots(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Return the top-N most frequently changed files."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT file_path, change_count FROM hotspots "
            "ORDER BY change_count DESC LIMIT ?",
            (limit,),
        )
        results = cursor.fetchall()
        conn.close()
        return results

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from joomha.retriever.vector import VectorRetriever
from joomha.retriever.graph import GraphRetriever
from joomha.llm.client import LLMClient
from joomha.llm.prompt_builder import build_prompt


class Orchestrator:
    """Central coordinator for the Joomha Q&A pipeline."""

    def __init__(
        self,
        repo_root: str,
        db_path: str,
        lancedb_dir: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.repo_root = repo_root
        self.db_path = db_path
        self.lancedb_dir = lancedb_dir
        self.joomha_dir = Path(repo_root) / ".joomha"
        # Bug L: switched to .jsonl extension
        self.session_log_path = self.joomha_dir / "session_log.jsonl"

        self.current_mode = "graph"  # default mode

        # Bug 6: conversation history buffer (kept in memory for the session)
        self._conversation_history: List[Dict[str, str]] = []
        self._max_history_turns = 5  # keep last N exchanges to limit token usage

        # Initialise components
        self.vector_retriever = VectorRetriever(lancedb_dir)
        self.graph_retriever = GraphRetriever(db_path, repo_root)
        self.llm_client = LLMClient(provider=provider, model=model)

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
    # Bug 6: Conversation history helpers
    # ------------------------------------------------------------------

    def _build_history_context(self) -> str:
        """Format the last N conversation turns for the prompt."""
        if not self._conversation_history:
            return ""
        parts = ["## Riwayat Percakapan (untuk konteks follow-up)\n"]
        for turn in self._conversation_history[-self._max_history_turns:]:
            parts.append(f"**User:** {turn['query']}")
            # Truncate long answers to save tokens
            answer_preview = turn["answer"][:300]
            if len(turn["answer"]) > 300:
                answer_preview += "..."
            parts.append(f"**Joomha:** {answer_preview}\n")
        return "\n".join(parts)

    def _record_turn(self, query: str, answer: str) -> None:
        """Append a turn to the in-memory conversation history."""
        self._conversation_history.append({
            "query": query,
            "answer": answer,
        })

    # ------------------------------------------------------------------
    # Logging  (Bug L: JSONL append-only)
    # ------------------------------------------------------------------

    def _log_interaction(self, query: str, result: Dict) -> None:
        """Append this Q&A turn to session_log.jsonl (one JSON object per line)."""
        log_entry = {
            "query": query,
            "mode": result.get("mode_used", ""),
            "answer": result.get("answer", "")[:500],
            "latency": result.get("latency", 0),
            "context_count": result.get("context_count", 0),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        self.joomha_dir.mkdir(parents=True, exist_ok=True)
        # Bug L: append a single JSON line instead of rewriting the entire file
        with open(self.session_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

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

        # Bug 6: include conversation history in the prompt
        history_ctx = self._build_history_context()
        prompt = build_prompt(query, context, mode_used, history=history_ctx)
        answer, latency = self.llm_client.generate(prompt)

        # Bug 6: record this turn
        self._record_turn(query, answer)

        result = {
            "answer": answer,
            "mode_used": mode_used,
            "latency": latency,
            "context_count": len(context),
        }
        self._log_interaction(query, result)
        return result

    def _ask_compare(self, query: str) -> Dict:
        """Run both retrievers side-by-side and return combined answer.

        Bug 7:  LLM calls run concurrently via ThreadPoolExecutor.
        Bug I:  When graph falls back to vector, we reuse the already-fetched
                vector context instead of calling vector retriever again.
        """
        # Retrieve contexts
        v_context = self.vector_retriever.retrieve(query)
        g_context = self.graph_retriever.retrieve(query)
        g_mode = "graph"

        # Bug I: If graph is empty, reuse v_context instead of calling vector again
        if not g_context:
            g_context = v_context  # reuse — no extra retriever call
            g_mode = "vector (fallback)"

        history_ctx = self._build_history_context()
        v_prompt = build_prompt(query, v_context, "vector", history=history_ctx)
        g_prompt = build_prompt(query, g_context, g_mode, history=history_ctx)

        # Bug 7: concurrent LLM calls
        with ThreadPoolExecutor(max_workers=2) as pool:
            future_v = pool.submit(self.llm_client.generate, v_prompt)
            future_g = pool.submit(self.llm_client.generate, g_prompt)
            v_answer, v_latency = future_v.result()
            g_answer, g_latency = future_g.result()

        combined_answer = (
            f"## 🔵 Vector Retrieval\n{v_answer}\n\n"
            f"---\n\n"
            f"## 🟢 Graph Retrieval ({g_mode})\n{g_answer}"
        )

        # Bug 6: record this turn
        self._record_turn(query, combined_answer)

        result = {
            "answer": combined_answer,
            "mode_used": "compare",
            "latency": max(v_latency, g_latency),  # concurrent → take the longer one
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

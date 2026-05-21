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
    """Koordinator utama sistem Q&A"""

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
        # Ubah ke ekstensi JSONL
        self.session_log_path = self.joomha_dir / "session_log.jsonl"

        self.current_mode = "graph"  # Mode bawaan

        # Buffer riwayat percakapan di RAM
        self._conversation_history: List[Dict[str, str]] = []
        self._max_history_turns = 5  # Batasi riwayat percakapan untuk hemat token

        # Inisialisasi komponen
        self.vector_retriever = VectorRetriever(lancedb_dir)
        self.graph_retriever = GraphRetriever(db_path, repo_root)
        self.llm_client = LLMClient(provider=provider, model=model)

    # ------------------------------------------------------------------
    # Manajemen mode
    # ------------------------------------------------------------------

    def set_mode(self, mode: str) -> str:
        """Ubah mode pencarian"""
        if mode in ("vector", "graph", "compare"):
            self.current_mode = mode
            return f"Mode diubah ke: {mode}"
        return f"Mode tidak valid: {mode}. Gunakan: vector, graph, compare"

    # ------------------------------------------------------------------
    # Pembantu riwayat percakapan
    # ------------------------------------------------------------------

    def _build_history_context(self) -> str:
        """Format riwayat percakapan sebelumnya"""
        if not self._conversation_history:
            return ""
        parts = ["## Riwayat Percakapan (untuk konteks follow-up)\n"]
        for turn in self._conversation_history[-self._max_history_turns:]:
            parts.append(f"**User:** {turn['query']}")
            # Potong teks jawaban panjang
            answer_preview = turn["answer"][:300]
            if len(turn["answer"]) > 300:
                answer_preview += "..."
            parts.append(f"**Joomha:** {answer_preview}\n")
        return "\n".join(parts)

    def _record_turn(self, query: str, answer: str) -> None:
        """Sisipkan obrolan ke riwayat memory"""
        self._conversation_history.append({
            "query": query,
            "answer": answer,
        })

    # ------------------------------------------------------------------
    # Pencatatan log
    # ------------------------------------------------------------------

    def _log_interaction(self, query: str, result: Dict) -> None:
        """Tambahkan log Q&A per baris"""
        log_entry = {
            "query": query,
            "mode": result.get("mode_used", ""),
            "answer": result.get("answer", "")[:500],
            "latency": result.get("latency", 0),
            "context_count": result.get("context_count", 0),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        self.joomha_dir.mkdir(parents=True, exist_ok=True)
        # Tempel log tanpa ubah keseluruhan file
        with open(self.session_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Eksekusi Kueri
    # ------------------------------------------------------------------

    def ask(self, query: str) -> Dict:
        """Jalankan jalur sistem RAG utama"""
        if self.current_mode == "compare":
            return self._ask_compare(query)
        if self.current_mode == "vector":
            return self._ask_single(query, "vector")
        # Default: grafis dengan fallback otomatis
        return self._ask_single(query, "graph")

    def _ask_single(self, query: str, mode: str) -> Dict:
        """Jalankan kueri dalam satu mode (vektor/graf)"""
        mode_used = mode

        if mode == "graph":
            context = self.graph_retriever.retrieve(query)
            if not context:
                # [INFO] Automatic fallback — this is a feature, not an error.
                context = self.vector_retriever.retrieve(query)
                mode_used = "vector (fallback)"
        else:
            context = self.vector_retriever.retrieve(query)

        # Sertakan riwayat percakapan
        history_ctx = self._build_history_context()
        prompt = build_prompt(query, context, mode_used, history=history_ctx)
        answer, latency = self.llm_client.generate(prompt)

        # Catat percakapan ini
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
        """Jalankan kedua pencari dan gabungkan hasil"""

        # Ambil Konteks
        v_context = self.vector_retriever.retrieve(query)
        g_context = self.graph_retriever.retrieve(query)
        g_mode = "graph"

        # Gunakan ulang konteks vektor jika graf kosong
        if not g_context:
            g_context = v_context  # [INFO] reuse — no extra retriever call
            g_mode = "vector (fallback)"

        history_ctx = self._build_history_context()
        v_prompt = build_prompt(query, v_context, "vector", history=history_ctx)
        g_prompt = build_prompt(query, g_context, g_mode, history=history_ctx)

        # Pemanggilan LLM secara konkuren
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

        # Catat percakapan ini
        self._record_turn(query, combined_answer)

        result = {
            "answer": combined_answer,
            "mode_used": "compare",
            "latency": max(v_latency, g_latency),  # [INFO] concurrent → take the longer one
            "context_count": len(v_context) + len(g_context),
            "vector_answer": v_answer,
            "graph_answer": g_answer,
            "vector_latency": v_latency,
            "graph_latency": g_latency,
        }
        self._log_interaction(query, result)
        return result

    # ------------------------------------------------------------------
    # Kueri utilitas
    # ------------------------------------------------------------------

    def get_hotspots(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Ambil file yang paling sering diubah"""
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

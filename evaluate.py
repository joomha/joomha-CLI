import csv
import json
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Bug H: Retry helper with exponential backoff
# ---------------------------------------------------------------------------

def _retry_generate(llm_client, prompt: str, max_retries: int = 3):
    """Call llm_client.generate with retries and exponential backoff.

    Returns (answer, latency) or a fallback error tuple after all retries.
    """
    for attempt in range(max_retries):
        answer, latency = llm_client.generate(prompt)
        if not answer.startswith("[Error dari LLM]"):
            return answer, latency
        if attempt < max_retries - 1:
            wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
            print(f"    ⚠ Retry {attempt + 1}/{max_retries} setelah {wait}s...")
            time.sleep(wait)
    return answer, latency  # return last failure


def main() -> None:
    # ------------------------------------------------------------------
    # Load test questions
    # ------------------------------------------------------------------
    questions_file = Path("test_questions.json")
    if not questions_file.exists():
        print("Error: test_questions.json tidak ditemukan!")
        sys.exit(1)

    questions = json.loads(questions_file.read_text(encoding="utf-8"))
    print(f"Loaded {len(questions)} pertanyaan dari test_questions.json\n")

    # ------------------------------------------------------------------
    # Verify index exists
    # ------------------------------------------------------------------
    repo_root = Path.cwd()
    joomha_dir = repo_root / ".joomha"
    db_path = str(joomha_dir / "index.db")
    lancedb_dir = str(joomha_dir / "lancedb")

    if not joomha_dir.exists():
        print("Error: Jalankan 'joomha' terlebih dahulu untuk indexing.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Init retrievers & LLM
    # ------------------------------------------------------------------
    from joomha.retriever.vector import VectorRetriever
    from joomha.retriever.graph import GraphRetriever
    from joomha.llm.client import LLMClient
    from joomha.llm.prompt_builder import build_prompt

    vector_retriever = VectorRetriever(lancedb_dir)
    graph_retriever = GraphRetriever(db_path, str(repo_root))
    llm_client = LLMClient()

    # ------------------------------------------------------------------
    # Bug H: inter-call delay to respect API rate limits
    # ------------------------------------------------------------------
    API_CALL_DELAY = 1.5  # seconds between consecutive calls

    # ------------------------------------------------------------------
    # Bug S: evaluate 3 modes: vector, graph, compare
    # ------------------------------------------------------------------
    results: list[dict] = []

    for i, q in enumerate(questions, 1):
        query = q["query"]
        ground_truth = q.get("ground_truth", "")
        relevant_files = q.get("relevant_files", [])

        print(f"[{i}/{len(questions)}] {query[:70]}...")

        for mode in ("vector", "graph", "compare"):
            start = time.time()
            actual_mode = mode

            if mode == "vector":
                context = vector_retriever.retrieve(query)

            elif mode == "graph":
                context = graph_retriever.retrieve(query)
                if not context:
                    context = vector_retriever.retrieve(query)
                    actual_mode = "vector (fallback)"

            else:  # compare
                # For compare mode: use both contexts concatenated for metrics
                v_ctx = vector_retriever.retrieve(query)
                g_ctx = graph_retriever.retrieve(query)
                if not g_ctx:
                    g_ctx = v_ctx
                context = v_ctx + g_ctx  # combined for file-hit metrics

            prompt = build_prompt(query, context, actual_mode)
            answer, llm_latency = _retry_generate(llm_client, prompt)

            total_latency = time.time() - start

            # ── Metrics ───────────────────────────────────────────────
            retrieved_files = [c.get("file_path", "") for c in context]

            # Hit Rate: 1 if *any* relevant file appears in retrieved context
            hit = int(any(rf in retrieved_files for rf in relevant_files))

            # MRR: reciprocal rank of the first relevant file found
            mrr = 0.0
            for rank, rf in enumerate(retrieved_files, 1):
                if rf in relevant_files:
                    mrr = 1.0 / rank
                    break

            results.append({
                "query": query,
                "mode": actual_mode,
                "answer": answer[:500],
                "latency_s": round(total_latency, 3),
                "hit_rate": hit,
                "mrr": round(mrr, 4),
                "context_count": len(context),
                "ground_truth": ground_truth[:200],
            })

            # Bug H: delay between API calls to avoid rate limits
            time.sleep(API_CALL_DELAY)

    # ------------------------------------------------------------------
    # Bug G: Guard against empty results before writing CSV
    # ------------------------------------------------------------------
    output_file = "hasil_evaluasi.csv"

    if not results:
        print("\n⚠ Semua API call gagal. Tidak ada hasil untuk disimpan.")
        sys.exit(1)

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    # ------------------------------------------------------------------
    # Print summary
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f">> Evaluasi selesai! Hasil disimpan ke: {output_file}")
    print(f"  Total runs: {len(results)}")

    def _summarise(mode_filter: set):
        hits = [r["hit_rate"] for r in results if r["mode"] in mode_filter]
        mrrs = [r["mrr"] for r in results if r["mode"] in mode_filter]
        lats = [r["latency_s"] for r in results if r["mode"] in mode_filter]
        if hits:
            avg_hit = sum(hits) / len(hits)
            avg_mrr = sum(mrrs) / len(mrrs)
            avg_lat = sum(lats) / len(lats)
            return avg_hit, avg_mrr, avg_lat
        return None

    for label, modes in [
        ("Vector", {"vector"}),
        ("Graph", {"graph", "vector (fallback)"}),
        ("Compare", {"compare"}),
    ]:
        stats = _summarise(modes)
        if stats:
            print(
                f"  {label:8s} — Hit Rate: {stats[0]:.2%}  "
                f"MRR: {stats[1]:.4f}  "
                f"Avg Latency: {stats[2]:.2f}s"
            )

    print(f"{'='*60}")


if __name__ == "__main__":
    main()

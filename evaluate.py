"""Batch evaluator for Joomha retrieval comparison (research instrument).

Usage:
    1. Index a target repo with `joomha` first.
    2. Fill test_questions.json with 30 question/ground-truth pairs.
    3. Run: python evaluate.py
    4. Results are saved to hasil_evaluasi.csv
"""

import csv
import json
import sys
import time
from pathlib import Path


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
    # Run evaluation: each question × 2 modes
    # ------------------------------------------------------------------
    results: list[dict] = []

    for i, q in enumerate(questions, 1):
        query = q["query"]
        ground_truth = q.get("ground_truth", "")
        relevant_files = q.get("relevant_files", [])

        print(f"[{i}/{len(questions)}] {query[:70]}...")

        for mode in ("vector", "graph"):
            start = time.time()
            actual_mode = mode

            if mode == "vector":
                context = vector_retriever.retrieve(query)
            else:
                context = graph_retriever.retrieve(query)
                if not context:
                    context = vector_retriever.retrieve(query)
                    actual_mode = "vector (fallback)"

            prompt = build_prompt(query, context, actual_mode)
            answer, llm_latency = llm_client.generate(prompt)
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

    # ------------------------------------------------------------------
    # Write CSV
    # ------------------------------------------------------------------
    output_file = "hasil_evaluasi.csv"
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

    v_hits = [r["hit_rate"] for r in results if r["mode"] == "vector"]
    g_hits = [
        r["hit_rate"]
        for r in results
        if r["mode"] in ("graph", "vector (fallback)")
    ]
    v_mrr = [r["mrr"] for r in results if r["mode"] == "vector"]
    g_mrr = [
        r["mrr"]
        for r in results
        if r["mode"] in ("graph", "vector (fallback)")
    ]
    v_lat = [r["latency_s"] for r in results if r["mode"] == "vector"]
    g_lat = [
        r["latency_s"]
        for r in results
        if r["mode"] in ("graph", "vector (fallback)")
    ]

    if v_hits:
        print(f"  Vector — Hit Rate: {sum(v_hits)/len(v_hits):.2%}  "
              f"MRR: {sum(v_mrr)/len(v_mrr):.4f}  "
              f"Avg Latency: {sum(v_lat)/len(v_lat):.2f}s")
    if g_hits:
        print(f"  Graph  — Hit Rate: {sum(g_hits)/len(g_hits):.2%}  "
              f"MRR: {sum(g_mrr)/len(g_mrr):.4f}  "
              f"Avg Latency: {sum(g_lat)/len(g_lat):.2f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

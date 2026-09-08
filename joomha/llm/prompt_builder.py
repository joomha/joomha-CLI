"""[PENANDA]"""


import os
from typing import List, Dict

PROMPT_FILE_PATH = os.path.join(os.path.dirname(__file__), "system_prompt.txt")

try:
    with open(PROMPT_FILE_PATH, "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read().strip()
except FileNotFoundError:
    SYSTEM_PROMPT = "System prompt file not found."


def _format_vector_context(results: List[Dict]) -> str:
    """Format hasil pencarian vektor"""
    if not results:
        return "(Tidak ada konteks yang ditemukan)"

    parts: list[str] = []
    for i, r in enumerate(results, 1):
        parts.append(
            f"--- Chunk {i} ---\n"
            f"File: {r['file_path']} "
            f"(baris {r.get('start_line', '?')}-{r.get('end_line', '?')})\n"
            f"Skor kemiripan: {r.get('score', 'N/A')}\n"
            f"```\n{r['text']}\n```"
        )
    return "\n\n".join(parts)


def _format_graph_context(results: List[Dict]) -> str:
    """Format konteks graf relasi"""
    if not results:
        return "(Tidak ada konteks yang ditemukan)"

    parts: list[str] = []
    for i, r in enumerate(results, 1):
        importers_str = ", ".join(r.get("importers", [])) or "tidak ada"
        cochanges_items = r.get("cochanges", [])
        cochanges_str = (
            ", ".join(
                f"{c['file']} (skor: {c['score']})" for c in cochanges_items
            )
            or "tidak ada"
        )

        parts.append(
            f"--- Node {i} ---\n"
            f"File: {r['file_path']} "
            f"({r.get('node_type', '?')}: {r.get('node_name', '?')})\n"
            f"Baris: {r.get('start_line', '?')}-{r.get('end_line', '?')}\n"
            f"Di-import oleh: {importers_str}\n"
            f"Sering berubah bersama: {cochanges_str}\n"
            f"```\n{r['text']}\n```"
        )
    return "\n\n".join(parts)


def build_prompt(
    query: str,
    context_results: List[Dict],
    mode: str,
    history: str = "",
) -> str:
    """[PENANDA]"""

    if mode in ("vector", "vector (fallback)"):
        context_text = _format_vector_context(context_results)
    else:
        context_text = _format_graph_context(context_results)

    # Tambahkan riwayat percakapan
    history_block = f"\n{history}\n" if history else ""

    return (
        f"{SYSTEM_PROMPT}\n"
        f"{history_block}\n"
        f"KONTEKS:\n{context_text}\n\n"
        f"PERTANYAAN:\n{query}\n\n"
        f"JAWABAN:"
    )

"""Prompt builder — constructs an IDENTICAL prompt structure for both retrieval modes.

This is critical for research validity: the wrapper prompt is always the same;
only the formatted context block differs between vector and graph mode.
"""

from typing import List, Dict

SYSTEM_PROMPT = (
    "Kamu adalah Joomha, seorang senior software engineer dengan keahlian "
    "mendalam dalam membaca, memahami, dan menjelaskan arsitektur kode sumber.\n\n"

    "## Tugas Utama\n"
    "Jawab pertanyaan pengguna tentang repositori kode **hanya berdasarkan "
    "potongan kode (konteks) yang disediakan di bawah**. Jangan mengarang "
    "informasi yang tidak ada di dalam konteks.\n\n"

    "## Aturan Menjawab\n"
    "1. **Grounding** — Setiap klaim harus bisa dilacak ke potongan kode "
    "di konteks. Sebutkan nama file dan nomor baris saat merujuk kode, "
    "contoh: `auth_handler.py (baris 42-58)`.\n"
    "2. **Bahasa** — Jawab menggunakan bahasa yang sama dengan pertanyaan "
    "pengguna (Indonesia/Inggris).\n"
    "3. **Kejujuran** — Jika konteks yang diberikan tidak cukup untuk "
    "menjawab secara akurat, katakan: \"Informasi di konteks tidak cukup "
    "untuk menjawab pertanyaan ini dengan pasti.\" Jangan berspekulasi.\n"
    "4. **Struktur jawaban** — Gunakan heading, bullet point, dan blok kode "
    "markdown agar jawaban mudah dibaca di terminal.\n"
    "5. **Fokus** — Jawab langsung ke inti pertanyaan. Hindari pembukaan "
    "basa-basi yang tidak perlu.\n"
    "6. **Relasi antar file** — Jika konteks menyertakan informasi tentang "
    "import, co-change, atau dependensi antar file, manfaatkan informasi "
    "tersebut untuk memberikan gambaran arsitektural yang lebih kaya.\n"
)


def _format_vector_context(results: List[Dict]) -> str:
    """Format vector retrieval results into a context string."""
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
    """Format graph retrieval results into a context string (includes relationship metadata)."""
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


def build_prompt(query: str, context_results: List[Dict], mode: str) -> str:
    """Build the final prompt sent to the LLM.

    The wrapper structure (SYSTEM_PROMPT + KONTEKS + PERTANYAAN + JAWABAN)
    is **identical** for every mode — only the context block changes.
    """
    if mode in ("vector", "vector (fallback)"):
        context_text = _format_vector_context(context_results)
    else:
        context_text = _format_graph_context(context_results)

    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"KONTEKS:\n{context_text}\n\n"
        f"PERTANYAAN:\n{query}\n\n"
        f"JAWABAN:"
    )

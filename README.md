# Joomha

**AI-powered CLI for understanding any codebase through conversation.**

Joomha adalah tool CLI berbasis Python yang memungkinkan siapa pun memahami repositori kode asing hanya dengan bertanya dalam bahasa natural. Dibangun di atas arsitektur RAG (Retrieval-Augmented Generation) dengan dua mesin retrieval yang bisa dibandingkan: **Vector Retrieval** dan **Graph Retrieval**.

---

##  Fitur Utama

-  **Vector Retrieval** — Cosine similarity search menggunakan `all-MiniLM-L6-v2` embeddings
-  **Graph Retrieval** — Traversal relasional via AST parsing + Git co-change analysis
-  **Compare Mode** — Jalankan kedua retriever sekaligus dan bandingkan hasilnya
-  **Auto Fallback** — Graph → Vector secara otomatis jika tidak ada node yang cocok
-  **Rich TUI** — Banner, panel berwarna, spinner, tabel — semua di terminal
-  **Research-ready** — Evaluator bawaan untuk riset perbandingan retrieval

---

##  Instalasi

### Dari Source (Development)

```bash
git clone https://github.com/username/joomha.git
cd joomha
pip install -e .
```

### Dari PyPI

```bash
pip install joomha
```

---

##  Konfigurasi

Joomha membutuhkan API key untuk LLM. Pilih salah satu provider:

### Via Environment Variable (Direkomendasikan)

```bash
# Google Gemini (default, gratis)
export GEMINI_API_KEY=your-key-here

# Atau OpenAI
export OPENAI_API_KEY=your-key-here

# Atau Anthropic
export ANTHROPIC_API_KEY=your-key-here
```

### Via CLI

```bash
joomha config set gemini your-key-here
joomha config show
```

---

##  Penggunaan

### Memulai

```bash
cd /path/to/any/git/repo
joomha
```

Saat pertama kali dijalankan, Joomha akan otomatis:
1. Parsing AST semua file Python
2. Menganalisis riwayat Git (co-changes, hotspots)
3. Membangun vector embeddings

### REPL Commands

| Command | Deskripsi |
|---------|-----------|
| `<pertanyaan>` | Tanya apapun tentang kode |
| `/mode vector` | Gunakan Vector Retrieval |
| `/mode graph` | Gunakan Graph Retrieval |
| `/mode compare` | Bandingkan kedua mode |
| `/hotspots` | Tampilkan file paling sering diubah |
| `/help` | Tampilkan bantuan |
| `/q` | Keluar |

### Contoh Sesi

```
[graph] ❯ Bagaimana cara kerja sistem autentikasi?

╭──── Joomha [graph] ────╮
│                         │
│  Sistem autentikasi...  │
│                         │
╰─ Mode: graph │ Konteks: 3 │ Latency: 1.23s ─╯

[graph] ❯ /mode compare
✓ Mode diubah ke: compare

[compare] ❯ Jelaskan alur request handling
```

### Re-indexing

```bash
joomha --reindex
```

---

##  Evaluasi Riset

Joomha menyertakan evaluator untuk riset perbandingan retrieval:

1. Edit `test_questions.json` dengan 30 pertanyaan + ground truth
2. Jalankan evaluator:

```bash
python evaluate.py
```

3. Hasil tersimpan di `hasil_evaluasi.csv` dengan metrik:
   - **Hit Rate** — Apakah file relevan ada di konteks?
   - **MRR** — Posisi file relevan pertama
   - **Latency** — Waktu total per query

---

##  Arsitektur

```
Query ──┬── VectorRetriever ── LanceDB cosine search ── Top-5 chunks
        │
        └── GraphRetriever ── SQLite (AST nodes + edges + co-changes)
                │
                └── Fallback ke VectorRetriever jika kosong
                         │
                         ▼
              PromptBuilder (struktur IDENTIK)
                         │
                         ▼
                  LLMClient (Gemini/OpenAI/Claude)
                         │
                         ▼
                   Rich Markdown Output
```

---

##  Struktur Proyek

```
joomha/
├── joomha/
│   ├── cli.py              # Entry point + REPL
│   ├── config.py           # API key management
│   ├── orchestrator.py     # RAG pipeline coordinator
│   ├── indexer/
│   │   ├── ast_parser.py   # Python AST → SQLite
│   │   ├── git_analyzer.py # Git history → SQLite
│   │   └── vector_builder.py  # Code → embeddings → LanceDB
│   ├── retriever/
│   │   ├── vector.py       # Cosine similarity retrieval
│   │   └── graph.py        # Relational graph retrieval
│   ├── llm/
│   │   ├── client.py       # Multi-provider LLM client
│   │   └── prompt_builder.py  # Identical prompt structure
│   └── ui/
│       ├── display.py      # Rich panels & tables
│       └── input_handler.py   # prompt-toolkit session
├── evaluate.py             # Research evaluation script
├── test_questions.json     # Evaluation dataset
├── pyproject.toml
└── README.md
```

---

##  Stack Teknologi

| Layer | Library |
|-------|---------|
| CLI | typer, rich, prompt-toolkit |
| AST | ast (stdlib) |
| Git | gitpython |
| Embedding | sentence-transformers (all-MiniLM-L6-v2) |
| Vector DB | lancedb + pyarrow |
| Graph DB | sqlite3 (stdlib) |
| LLM | google-generativeai / openai / anthropic |

---


MIT License — lihat [LICENSE](LICENSE) untuk detail.

---

*Joomha v1.0 — Bangun dengan Python, untuk memahami kode tanpa harus membacanya baris per baris.* 🚀

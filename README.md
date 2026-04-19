<<<<<<< HEAD
# Joomha

**AI-powered CLI for understanding any codebase through conversation.**

Joomha adalah tool AI CLI yang memungkinkan memahami repositori kode asing hanya dengan bertanya dalam bahasa natural. Dibangun di atas arsitektur RAG (Retrieval-Augmented Generation) dengan dua mesin retrieval yang bisa dibandingkan secara paralel: **Vector Retrieval** dan **Graph Retrieval**.

Dengan **Tree-sitter** memahami multi-bahasa: **Python, JavaScript (.js, .jsx), dan TypeScript (.ts, .tsx)**.

---

## Fitur Utama

- **Vector Retrieval** — Cosine similarity search menggunakan `all-MiniLM-L6-v2` embeddings
- **Graph Retrieval** — Traversal relasional via AST parsing + Git co-change analysis
- **Compare Mode** — Jalankan kedua retriever sekaligus dan bandingkan hasilnya
- **Auto Fallback** — Graph → Vector secara otomatis jika tidak ada node yang cocok
- **Rich TUI** — Banner, panel berwarna, spinner, tabel — semua di terminal
- **Research-ready** — Evaluator bawaan untuk riset perbandingan retrieval

---

## Instalasi
=======
# joomha-CLI

**AI-powered CLI for understanding any codebase through conversation.**

joomha-CLI adalah tool CLI berbasis Python yang memungkinkan siapa pun memahami repositori kode asing hanya dengan bertanya dalam bahasa natural. Dibangun di atas arsitektur RAG (Retrieval-Augmented Generation) dengan dua mesin retrieval yang bisa dibandingkan: **Vector Retrieval** dan **Graph Retrieval**.

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
>>>>>>> 4e1c0a63a8a67afc61c5dcbba64f9560357a0971

### Dari Source (Development)

```bash
<<<<<<< HEAD
git clone https://github.com/joomha/joomha-CLI.git
=======
git clone https://github.com/username/joomha-CLI.git](https://github.com/joomha/joomha-CLI.git
>>>>>>> 4e1c0a63a8a67afc61c5dcbba64f9560357a0971
cd joomha-CLI
pip install -e .
```

### Dari PyPI

```bash
pip install joomha-CLI
```

---

<<<<<<< HEAD
## Konfigurasi
=======
##  Konfigurasi
>>>>>>> 4e1c0a63a8a67afc61c5dcbba64f9560357a0971

joomha-CLI membutuhkan API key untuk LLM. Pilih salah satu provider:

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

<<<<<<< HEAD
## Penggunaan
=======
##  Penggunaan
>>>>>>> 4e1c0a63a8a67afc61c5dcbba64f9560357a0971

### Memulai

```bash
cd /path/to/any/git/repo
joomh
```

<<<<<<< HEAD
Saat pertama kali dijalankan, Joomha akan otomatis:

=======
Saat pertama kali dijalankan, joomha-CLI akan otomatis:
>>>>>>> 4e1c0a63a8a67afc61c5dcbba64f9560357a0971
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

╭──── joomha-CLI [graph] ────╮
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

<<<<<<< HEAD
## Arsitektur
=======
##  Arsitektur
>>>>>>> 4e1c0a63a8a67afc61c5dcbba64f9560357a0971

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

<<<<<<< HEAD
## Struktur Proyek

```text
joomha/
=======
##  Struktur Proyek

```

>>>>>>> 4e1c0a63a8a67afc61c5dcbba64f9560357a0971
├── joomha/
│   ├── cli.py              # Entry point + REPL
│   ├── config.py           # API key management
│   ├── orchestrator.py     # RAG pipeline coordinator
│   ├── indexer/
│   │   ├── parsers/        # Multi-language AST Parsers
│   │   │   ├── base.py
│   │   │   ├── python_parser.py
│   │   │   ├── javascript_parser.py  # Tree-sitter powered
│   │   │   └── typescript_parser.py  # Tree-sitter powered
│   │   ├── ast_parser.py   # Universal Parser Dispatcher → SQLite
│   │   ├── git_analyzer.py # Git history → SQLite
│   │   └── vector_builder.py  # Multi-lang chunking → LanceDB
│   ├── retriever/
│   │   ├── vector.py       # Cosine similarity retrieval
│   │   └── graph.py        # Relational graph retrieval
│   ├── llm/
│   │   ├── client.py       # Multi-provider LLM client
│   │   └── prompt_builder.py  # Strict grounding & AI Persona prompt
│   └── ui/
│       ├── display.py      # Rich panels & tables
│       └── input_handler.py   # prompt-toolkit session
├── evaluate.py             # Research evaluation script
├── test_questions.json     # Evaluation dataset
├── pyproject.toml
└── README.md
```

---

<<<<<<< HEAD
## Stack Teknologi
=======
##  Stack Teknologi
>>>>>>> 4e1c0a63a8a67afc61c5dcbba64f9560357a0971

| Layer | Library |
|-------|---------|
| CLI | typer, rich, prompt-toolkit |
| AST/Parser | tree-sitter (JS/TS), ast (Python stdlib) |
| Git | gitpython |
| Embedding | sentence-transformers (all-MiniLM-L6-v2) |
| Vector DB | lancedb + pyarrow |
| Graph DB | sqlite3 (stdlib) |
| LLM | google-generativeai (`gemini-flash-latest`) / openai / anthropic |

---
<<<<<<< HEAD
=======

>>>>>>> 4e1c0a63a8a67afc61c5dcbba64f9560357a0971

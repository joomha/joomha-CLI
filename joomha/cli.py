import warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

from pathlib import Path
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from joomha import __version__
from joomha.config import (
    get_api_key,
    set_api_key,
    get_active_provider,
    set_active_provider,
    get_active_model,
    set_active_model,
    get_all_configured_providers,
    get_custom_base_url,
    set_custom_base_url,
    PROVIDER_ENV_KEYS,
    MODEL_REGISTRY,
    OPEN_MODEL_PROVIDERS,
    ensure_joomha_gitignore,
)
from joomha.ui.display import (
    show_banner,
    show_answer,
    show_hotspots,
    show_help,
    show_mode_change,
    show_error,
    show_info,
    console as display_console,
)

# ---------------------------------------------------------------------------
# Aplikasi CLI Typer
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="joomha-AI",
    help="AI-powered CLI for understanding any codebase through conversation.",
    add_completion=False,
)

config_app = typer.Typer(help="Manage API keys and configuration.")
app.add_typer(config_app, name="config")

# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

JOOMHA_DIR = ".joomha"
DB_NAME = "index.db"
LANCEDB_DIR = "lancedb"
HISTORY_FILE = "input_history.txt"


# ---------------------------------------------------------------------------
# Fungsi pembantu
# ---------------------------------------------------------------------------

def _get_paths(repo_root: Path):
    """Dapatkan path file internal"""
    joomha_dir = repo_root / JOOMHA_DIR
    db_path = str(joomha_dir / DB_NAME)
    lancedb_dir = str(joomha_dir / LANCEDB_DIR)
    history_path = str(joomha_dir / HISTORY_FILE)
    return joomha_dir, db_path, lancedb_dir, history_path


def _run_indexing(
    repo_root: Path, joomha_dir: Path, db_path: str, lancedb_dir: str
) -> None:
    """Jalankan indexing menyeluruh"""
    from joomha.indexer.ast_parser import init_db, parse_repo
    from joomha.indexer.git_analyzer import analyze_git
    from joomha.indexer.vector_builder import build_vectors

    joomha_dir.mkdir(parents=True, exist_ok=True)

    # Pastikan .gitignore dibuat
    ensure_joomha_gitignore(joomha_dir)

    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=display_console,
    ) as progress:
        # 1. Persiapan Database
        task = progress.add_task("[cyan]Inisialisasi database...", total=1)
        conn = init_db(db_path)
        progress.update(task, advance=1, description="[green]✓ Database siap")

        # Ekstraksi AST
        task = progress.add_task("[cyan]Parsing AST kode sumber...", total=100)
        def ast_cb(count, total):
            progress.update(task, completed=count, total=total)
            if count > 0 and count == total:
                progress.update(task, description=f"[green]✓ AST parsed: {total} file")

        file_count = parse_repo(repo_root, conn, progress_callback=ast_cb)

        # Analisis Git
        task = progress.add_task("[cyan]Menganalisis riwayat git...", total=100)
        def git_cb(count, total):
            progress.update(task, completed=count, total=total)
            if count > 0 and count == total:
                progress.update(task, description=f"[green]✓ Git analyzed: {total} commit")

        commit_count = analyze_git(repo_root, conn, progress_callback=git_cb)
        conn.close()

        # Pembuatan vektor
        task = progress.add_task(
            "[cyan]Membangun vector embeddings...", total=100
        )
        def vec_cb(count, total):
            progress.update(task, completed=count, total=total)
            if count > 0 and count == total:
                progress.update(task, description=f"[green]✓ Vectors built: {total} chunks")

        chunk_count = build_vectors(repo_root, lancedb_dir, progress_callback=vec_cb)

    show_info(
        f"Indexing selesai! "
        f"({file_count} file, {commit_count} commit, {chunk_count} chunks)"
    )


# ---------------------------------------------------------------------------
# Pembantu ubah provider
# ---------------------------------------------------------------------------

def _show_provider_menu(orchestrator) -> None:
    """Tampilkan menu pemilihan provider/model"""
    from rich.table import Table

    configured = get_all_configured_providers()
    active_provider = orchestrator.llm_client.provider
    active_model = orchestrator.llm_client.model_id

    if not configured:
        show_error("Belum ada provider yang dikonfigurasi.")
        show_info("Jalankan: joomha config set <provider> <api_key>")
        return

    # Tampilkan status saat ini
    display_console.print(
        f"\n[bold cyan]Provider aktif:[/bold cyan] {active_provider} "
        f"([green]{active_model}[/green])\n"
    )

    # Tampilkan model provider
    table = Table(title="Provider & Model Tersedia", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Provider", style="cyan")
    table.add_column("Model", style="white")
    table.add_column("Tier", style="dim")
    table.add_column("Status", width=8)

    idx = 1
    choices = {}  # [INFO] idx → (provider, model_id)
    for provider in configured:
        models = MODEL_REGISTRY.get(provider, [{"id": "default", "label": "Default", "tier": "—"}])
        for m in models:
            is_active = (provider == active_provider and m["id"] == active_model)
            status = "[green]● aktif[/green]" if is_active else ""
            table.add_row(
                str(idx),
                provider,
                m["label"],
                m.get("tier", ""),
                status,
            )
            choices[idx] = (provider, m["id"])
            idx += 1

    display_console.print(table)
    display_console.print(
        "\n[dim]Ketik nomor untuk memilih, ATAU ketik langsung nama model (jika provider mendukung custom ID). ENTER batal:[/dim]"
    )


def _handle_provider_switch(user_input: str, orchestrator) -> bool:
    """Tangani input nomor pemilihan provider"""
    configured = get_all_configured_providers()
    choices = {}
    idx = 1
    for provider in configured:
        models = MODEL_REGISTRY.get(provider, [{"id": "default", "label": "Default", "tier": "—"}])
        for m in models:
            choices[idx] = (provider, m["id"])
            idx += 1

    try:
        choice = int(user_input.strip())
    except ValueError:
        custom_id = user_input.strip()
        if not custom_id:
            return False
            
        current_provider = orchestrator.llm_client.provider
        configured = get_all_configured_providers()
        
        # Deteksi pintar untuk OpenRouter
        # Gunakan ID model OpenRouter
        if "/" in custom_id and "openrouter" in configured and current_provider != "openrouter":
            current_provider = "openrouter"

        # Anggap custom model ID jika bukan angka
        # Pastikan dukungan model terbuka
        if current_provider in OPEN_MODEL_PROVIDERS:
            orchestrator.llm_client.switch(current_provider, custom_id)
            set_active_provider(current_provider)
            set_active_model(current_provider, custom_id)
            show_info(f"✓ Beralih ke custom model: {current_provider} ({custom_id})")
            return True
        else:
            show_error("Input harus berupa angka dari daftar di atas. Untuk string kustom, gunakan provider seperti OpenRouter.")
            return False

    if choice not in choices:
        show_error(f"Pilihan tidak valid: {choice}")
        return False

    new_provider, new_model = choices[choice]
    try:
        orchestrator.llm_client.switch(new_provider, new_model)
        set_active_provider(new_provider)
        set_active_model(new_provider, new_model)
        show_info(f"✓ Beralih ke: {new_provider} ({new_model})")
        return True
    except ValueError as e:
        show_error(str(e))
        return False


def _handle_slash_command(user_input: str, orchestrator) -> Optional[bool]:
    """[PENANDA]"""

    cmd = user_input.strip().lower()

    if cmd in ("/q", "/quit"):
        display_console.print("\n[dim]Sampai jumpa![/dim]")
        return False

    if cmd in ("/help", "/"):
        show_help()
        return True

    if cmd == "/hotspots":
        data = orchestrator.get_hotspots()
        show_hotspots(data)
        return True

    if cmd.startswith("/mode"):
        parts = cmd.split()
        if len(parts) == 2:
            mode = parts[1]
            msg = orchestrator.set_mode(mode)
            if "diubah" in msg:
                show_mode_change(mode)
            else:
                show_error(msg)
        else:
            show_error("Gunakan: /mode vector|graph|compare")
        return True

    if cmd == "/provider":
        _show_provider_menu(orchestrator)
        # Set flag untuk input pilihan angka
        orchestrator._awaiting_provider_choice = True
        return True

    if cmd == "/info":
        provider = orchestrator.llm_client.provider
        model = orchestrator.llm_client.model_id
        mode = orchestrator.current_mode
        show_info(f"Provider: {provider} │ Model: {model} │ Mode: {mode}")
        return True

    # Perintah tidak dikenali
    show_error(f"Perintah tidak dikenal: {cmd}. Ketik /help untuk bantuan.")
    return True


# ---------------------------------------------------------------------------
# Sub-perintah konfigurasi
# ---------------------------------------------------------------------------

@config_app.command("set")
def config_set(
    provider: str = typer.Argument(
        ..., help="Provider: gemini, openai, anthropic, deepseek, openrouter, custom"
    ),
    key: str = typer.Argument(..., help="API key"),
) -> None:
    """Atur API key provider"""
    if provider not in PROVIDER_ENV_KEYS:
        valid = ", ".join(PROVIDER_ENV_KEYS.keys())
        show_error(
            f"Provider tidak valid: {provider}. "
            f"Gunakan: {valid}"
        )
        raise typer.Exit(1)
    set_api_key(provider, key)
    show_info(f"API key untuk '{provider}' berhasil disimpan.")


@config_app.command("model")
def config_model(
    provider: str = typer.Argument(
        ..., help="Provider name (e.g. gemini, openai)"
    ),
    model_id: str = typer.Argument(
        ..., help="Model ID (e.g. gemini-2.5-pro, gpt-4o)"
    ),
) -> None:
    """Set model default untuk provider"""
    if provider not in MODEL_REGISTRY:
        show_error(f"Provider tidak dikenal: {provider}")
        raise typer.Exit(1)
        
    if provider not in OPEN_MODEL_PROVIDERS:
        valid_ids = [m["id"] for m in MODEL_REGISTRY[provider]]
        if model_id not in valid_ids:
            show_error(f"Model '{model_id}' tidak tersedia untuk {provider}.")
            show_info(f"Pilihan: {', '.join(valid_ids)}")
            raise typer.Exit(1)
            
    set_active_model(provider, model_id)
    show_info(f"Model default untuk '{provider}' diubah ke: {model_id}")


@config_app.command("use")
def config_use(
    provider: str = typer.Argument(
        ..., help="Provider to set as active default"
    ),
) -> None:
    """Atur provider aktif default"""
    if provider not in PROVIDER_ENV_KEYS:
        valid = ", ".join(PROVIDER_ENV_KEYS.keys())
        show_error(f"Provider tidak valid: {provider}. Gunakan: {valid}")
        raise typer.Exit(1)
    if not get_api_key(provider):
        show_error(f"API key belum diset untuk '{provider}'.")
        show_info(f"Jalankan dulu: joomha config set {provider} <key>")
        raise typer.Exit(1)
    set_active_provider(provider)
    model = get_active_model(provider)
    show_info(f"Provider aktif diubah ke: {provider} (model: {model})")


@config_app.command("base-url")
def config_base_url(
    url: str = typer.Argument(..., help="Base URL for custom provider"),
) -> None:
    """Atur URL OpenAI custom"""
    set_custom_base_url(url)
    show_info(f"Custom base URL diset ke: {url}")


@config_app.command("show")
def config_show() -> None:
    """Tampilkan semua provider terpasang"""
    from rich.table import Table

    configured = get_all_configured_providers()
    active = get_active_provider()

    if not configured:
        show_info("Belum ada provider yang dikonfigurasi.")
        show_info("Jalankan: joomha config set <provider> <api_key>")
        return

    table = Table(title="Konfigurasi Joomha", show_lines=True)
    table.add_column("Provider", style="cyan")
    table.add_column("API Key", width=12)
    table.add_column("Model Aktif", style="white")
    table.add_column("Status")

    for provider in PROVIDER_ENV_KEYS:
        has_key = provider in configured
        model = get_active_model(provider) if has_key else "—"
        key_status = "[green]✓ tersedia[/green]" if has_key else "[dim]✗ belum diatur[/dim]"
        active_marker = "[bold green]● AKTIF[/bold green]" if provider == active else ""
        table.add_row(provider, key_status, model, active_marker)

    display_console.print(table)

    # Tampilkan URL dasar custom jika ada
    custom_url = get_custom_base_url()
    if custom_url:
        show_info(f"Custom base URL: {custom_url}")


# ---------------------------------------------------------------------------
# Perintah Utama
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    reindex: bool = typer.Option(
        False, "--reindex", help="Paksa re-index repositori"
    ),
    version: bool = typer.Option(
        False, "--version", "-v", help="Tampilkan versi"
    ),
    provider: Optional[str] = typer.Option(
        None, "--provider", "-p", help="Override provider (gemini/openai/anthropic/deepseek/openrouter/custom)"
    ),
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="Override model ID"
    ),
) -> None:
    """[PENANDA]"""

    # Lewati REPL jika subcommand digunakan
    if ctx.invoked_subcommand is not None:
        return

    if version:
        display_console.print(f"joomha v{__version__}")
        raise typer.Exit()

    repo_root = Path.cwd()

    # [INFO] ── Pre-flight checks ─────────────────────────────────────────────
    if not (repo_root / ".git").exists():
        show_error("Direktori ini bukan repositori Git.")
        show_info("Jalankan 'joomha' di dalam direktori yang memiliki .git")
        raise typer.Exit(1)

    # Tentukan provider dari konfigurasi
    active_prov = provider or get_active_provider()
    if not get_api_key(active_prov):
        show_error(f"API key belum diatur untuk provider '{active_prov}'.")
        env_key = PROVIDER_ENV_KEYS.get(active_prov, "")
        if env_key:
            show_info(f"Set via: export {env_key}=<key>")
        show_info(f"Atau: joomha config set {active_prov} <key>")

        # Tampilkan provider alternatif
        others = get_all_configured_providers()
        if others:
            show_info(f"Provider lain yang sudah dikonfigurasi: {', '.join(others)}")
            show_info(f"Gunakan: joomha --provider {others[0]}")
        else:
            display_console.print("\n[dim]ℹ Ingin menggunakan provider lain (openai, anthropic, deepseek, openrouter)?[/dim]")
            display_console.print("[dim]  1. Simpan key: [/dim][cyan]joomha config set <provider> <key>[/cyan]")
            display_console.print("[dim]  2. Jadikan default: [/dim][cyan]joomha config use <provider>[/cyan]")
            
        raise typer.Exit(1)

    # [INFO] ── Startup ───────────────────────────────────────────────────────
    show_banner()

    joomha_dir, db_path, lancedb_dir, history_path = _get_paths(repo_root)

    if reindex or not joomha_dir.exists():
        show_info("Memulai indexing repositori...")
        _run_indexing(repo_root, joomha_dir, db_path, lancedb_dir)
    else:
        # Beri peringatan jika data lawas
        db_file = joomha_dir / "index.db"
        if db_file.exists():
            idx_mtime = db_file.stat().st_mtime
            newest_src = 0.0
            for ext in (".py", ".js", ".ts", ".jsx", ".tsx"):
                for f in repo_root.rglob(f"*{ext}"):
                    try:
                        mt = f.stat().st_mtime
                        if mt > newest_src:
                            newest_src = mt
                    except OSError:
                        pass
            if newest_src > idx_mtime:
                show_info(
                    "⚠ Terdeteksi file yang lebih baru dari index. "
                    "Pertimbangkan --reindex untuk hasil akurat."
                )
            else:
                show_info("Index ditemukan. Gunakan --reindex untuk memperbarui.")
        else:
            show_info("Index ditemukan. Gunakan --reindex untuk memperbarui.")

    # [INFO] ── Init orchestrator ─────────────────────────────────────────────
    from joomha.orchestrator import Orchestrator

    try:
        with display_console.status("[cyan]Menghidupkan mesin AI (Loading Model)..."):
            orchestrator = Orchestrator(
                str(repo_root), db_path, lancedb_dir,
                provider=active_prov, model=model,
            )
    except ValueError as e:
        show_error(str(e))
        raise typer.Exit(1)

    # [INFO] ── Input session ─────────────────────────────────────────────────
    from joomha.ui.input_handler import create_session

    session = create_session(history_path)

    llm_info = orchestrator.llm_client.info()
    show_info(f"Mode: {orchestrator.current_mode} │ LLM: {llm_info}")
    show_info("Ketik pertanyaan, /help untuk bantuan, atau /provider untuk ganti LLM.\n")

    # [INFO] ── REPL loop ─────────────────────────────────────────────────────
    try:
        while True:
            try:
                mode_label = orchestrator.current_mode
                prov_short = orchestrator.llm_client.provider
                prompt_text = f"[{mode_label}│{prov_short}] ❯ "
                user_input = session.prompt(prompt_text)
            except EOFError:
                break

            if not user_input.strip():
                continue

            # Menunggu pilihan provider
            if getattr(orchestrator, '_awaiting_provider_choice', False):
                orchestrator._awaiting_provider_choice = False
                user_input_clean = user_input.strip()
                
                # Hapus tanda miring sebelum angka pilihan
                if user_input_clean.startswith("/") and user_input_clean[1:].isdigit():
                    user_input_clean = user_input_clean[1:]
                
                # Izinkan command lain lolos
                if user_input_clean.startswith("/") and not user_input_clean[1:].isdigit():
                    user_input = user_input_clean  # Lanjut ke handler perintah slash
                else:
                    _handle_provider_switch(user_input_clean, orchestrator)
                    continue

            # Perintah slash
            if user_input.strip().startswith("/"):
                result = _handle_slash_command(user_input, orchestrator)
                if result is False:
                    break
                continue

            # [INFO] Normal question → RAG pipeline
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=display_console,
            ) as progress:
                task = progress.add_task("[cyan]Berpikir...", total=None)
                response = orchestrator.ask(user_input.strip())
                progress.remove_task(task)

            show_answer(
                response["answer"],
                response["mode_used"],
                response["latency"],
                response["context_count"],
            )

    except KeyboardInterrupt:
        display_console.print("\n[dim]Sampai jumpa! [/dim]")


if __name__ == "__main__":
    app()

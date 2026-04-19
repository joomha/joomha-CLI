"""Joomha CLI — entry point with REPL loop, indexing, and slash commands."""

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

from pathlib import Path
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from joomha import __version__
from joomha.config import (
    get_api_key,
    set_api_key,
    get_active_provider,
    PROVIDER_ENV_KEYS,
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
# Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="joomha-AI",
    help="AI-powered CLI for understanding any codebase through conversation.",
    add_completion=False,
)

config_app = typer.Typer(help="Manage API keys and configuration.")
app.add_typer(config_app, name="config")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JOOMHA_DIR = ".joomha"
DB_NAME = "index.db"
LANCEDB_DIR = "lancedb"
HISTORY_FILE = "input_history.txt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_paths(repo_root: Path):
    """Derive all .joomha sub-paths from the repo root."""
    joomha_dir = repo_root / JOOMHA_DIR
    db_path = str(joomha_dir / DB_NAME)
    lancedb_dir = str(joomha_dir / LANCEDB_DIR)
    history_path = str(joomha_dir / HISTORY_FILE)
    return joomha_dir, db_path, lancedb_dir, history_path


def _run_indexing(
    repo_root: Path, joomha_dir: Path, db_path: str, lancedb_dir: str
) -> None:
    """Execute the full indexing pipeline (AST + Git + Vector)."""
    from joomha.indexer.ast_parser import init_db, parse_repo
    from joomha.indexer.git_analyzer import analyze_git
    from joomha.indexer.vector_builder import build_vectors

    joomha_dir.mkdir(parents=True, exist_ok=True)

    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=display_console,
    ) as progress:
        # 1. Database
        task = progress.add_task("[cyan]Inisialisasi database...", total=1)
        conn = init_db(db_path)
        progress.update(task, advance=1, description="[green]✓ Database siap")

        # 2. AST
        task = progress.add_task("[cyan]Parsing AST kode sumber...", total=100)
        def ast_cb(count, total):
            progress.update(task, completed=count, total=total)
            if count > 0 and count == total:
                progress.update(task, description=f"[green]✓ AST parsed: {total} file")

        file_count = parse_repo(repo_root, conn, progress_callback=ast_cb)

        # 3. Git
        task = progress.add_task("[cyan]Menganalisis riwayat git...", total=100)
        def git_cb(count, total):
            progress.update(task, completed=count, total=total)
            if count > 0 and count == total:
                progress.update(task, description=f"[green]✓ Git analyzed: {total} commit")

        commit_count = analyze_git(repo_root, conn, progress_callback=git_cb)
        conn.close()

        # 4. Vectors
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


def _handle_slash_command(user_input: str, orchestrator) -> Optional[bool]:
    """Process slash commands.

    Returns:
        True  — command handled, continue the REPL
        False — user wants to quit
        None  — input is not a slash command
    """
    cmd = user_input.strip().lower()

    if cmd in ("/q", "/quit"):
        display_console.print("\n[dim]Sampai jumpa![/dim]")
        return False

    if cmd == "/help":
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

    # Unknown slash command
    show_error(f"Perintah tidak dikenal: {cmd}. Ketik /help untuk bantuan.")
    return True


# ---------------------------------------------------------------------------
# Config sub-commands
# ---------------------------------------------------------------------------

@config_app.command("set")
def config_set(
    provider: str = typer.Argument(
        ..., help="Provider: gemini, openai, anthropic"
    ),
    key: str = typer.Argument(..., help="API key"),
) -> None:
    """Set API key for a provider."""
    if provider not in PROVIDER_ENV_KEYS:
        show_error(
            f"Provider tidak valid: {provider}. "
            "Gunakan: gemini, openai, anthropic"
        )
        raise typer.Exit(1)
    set_api_key(provider, key)
    show_info(f"API key untuk '{provider}' berhasil disimpan.")


@config_app.command("show")
def config_show() -> None:
    """Show current configuration."""
    provider = get_active_provider()
    has_key = bool(get_api_key(provider))
    show_info(f"Provider aktif: {provider}")
    key_status = "\u2713 tersedia" if has_key else "\u2717 belum diatur"
    show_info(f"API key: {key_status}")


# ---------------------------------------------------------------------------
# Main command
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
) -> None:
    """Joomha — Understand any codebase through conversation."""

    # If a subcommand like "config" is being invoked, skip REPL
    if ctx.invoked_subcommand is not None:
        return

    if version:
        display_console.print(f"joomha v{__version__}")
        raise typer.Exit()

    repo_root = Path.cwd()

    # ── Pre-flight checks ─────────────────────────────────────────────
    if not (repo_root / ".git").exists():
        show_error("Direktori ini bukan repositori Git.")
        show_info("Jalankan 'joomha' di dalam direktori yang memiliki .git")
        raise typer.Exit(1)

    provider = get_active_provider()
    if not get_api_key(provider):
        show_error(f"API key belum diatur untuk provider '{provider}'.")
        show_info(f"Set via: export {PROVIDER_ENV_KEYS[provider]}=<key>")
        show_info("Atau: joomha config set gemini <key>")
        raise typer.Exit(1)

    # ── Startup ───────────────────────────────────────────────────────
    show_banner()

    joomha_dir, db_path, lancedb_dir, history_path = _get_paths(repo_root)

    if reindex or not joomha_dir.exists():
        show_info("Memulai indexing repositori...")
        _run_indexing(repo_root, joomha_dir, db_path, lancedb_dir)
    else:
        show_info("Index ditemukan. Gunakan --reindex untuk memperbarui.")

    # ── Init orchestrator ─────────────────────────────────────────────
    from joomha.orchestrator import Orchestrator

    try:
        with display_console.status("[cyan]Menghidupkan mesin AI (Loading Model)..."):
            orchestrator = Orchestrator(str(repo_root), db_path, lancedb_dir)
    except ValueError as e:
        show_error(str(e))
        raise typer.Exit(1)

    # ── Input session ─────────────────────────────────────────────────
    from joomha.ui.input_handler import create_session

    session = create_session(history_path)

    show_info(f"Mode: {orchestrator.current_mode} │ Provider: {provider}")
    show_info("Ketik pertanyaan atau /help untuk bantuan.\n")

    # ── REPL loop ─────────────────────────────────────────────────────
    try:
        while True:
            try:
                mode_label = orchestrator.current_mode
                prompt_text = f"[{mode_label}] ❯ "
                user_input = session.prompt(prompt_text)
            except EOFError:
                break

            if not user_input.strip():
                continue

            # Slash commands
            if user_input.strip().startswith("/"):
                result = _handle_slash_command(user_input, orchestrator)
                if result is False:
                    break
                continue

            # Normal question → RAG pipeline
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
        display_console.print("\n[dim]Sampai jumpa! 👋[/dim]")


if __name__ == "__main__":
    app()

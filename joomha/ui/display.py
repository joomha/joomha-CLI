"""Rich display components — banners, panels, tables, progress indicators."""

import sys
import os

# Force UTF-8 on Windows to avoid cp1252 encoding errors
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.text import Text

console = Console()

BANNER = r"""
       ██╗ ██████╗  ██████╗ ███╗   ███╗██╗  ██╗ █████╗
       ██║██╔═══██╗██╔═══██╗████╗ ████║██║  ██║██╔══██╗
       ██║██║   ██║██║   ██║██╔████╔██║███████║███████║
  ██   ██║██║   ██║██║   ██║██║╚██╔╝██║██╔══██║██╔══██║
  ╚█████╔╝╚██████╔╝╚██████╔╝██║ ╚═╝ ██║██║  ██║██║  ██║
   ╚════╝  ╚═════╝  ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝
"""

MODE_COLORS = {
    "vector": "blue",
    "graph": "green",
    "vector (fallback)": "yellow",
    "compare": "magenta",
}


def show_banner() -> None:
    """Display the Joomha ASCII art banner at startup."""
    console.print(
        Panel(
            Text(BANNER, style="bold cyan", justify="center"),
            subtitle="[dim]AI-powered code comprehension · v1.0[/dim]",
            border_style="cyan",
        )
    )


def show_answer(answer: str, mode: str, latency: float, context_count: int) -> None:
    """Render the LLM answer inside a colour-coded Rich panel."""
    color = MODE_COLORS.get(mode, "white")
    md = Markdown(answer)
    footer = (
        f"[dim]Mode: {mode} │ Konteks: {context_count} │ "
        f"Latency: {latency:.2f}s[/dim]"
    )

    console.print()
    console.print(
        Panel(
            md,
            title=f"[bold {color}]Joomha [{mode}][/bold {color}]",
            subtitle=footer,
            border_style=color,
            padding=(1, 2),
        )
    )


def show_hotspots(data: list) -> None:
    """Display the file-hotspot leaderboard as a Rich table."""
    if not data:
        console.print("[yellow]Tidak ada data hotspot.[/yellow]")
        return

    table = Table(title="🔥 File Hotspots", border_style="red")
    table.add_column("#", style="dim", width=4)
    table.add_column("File", style="cyan")
    table.add_column("Changes", style="bold red", justify="right")

    for i, (fp, count) in enumerate(data, 1):
        table.add_row(str(i), fp, str(count))

    console.print(table)


def show_help() -> None:
    """Print the slash-command reference table."""
    table = Table(title="📖 Perintah Joomha", border_style="blue")
    table.add_column("Command", style="cyan bold")
    table.add_column("Deskripsi", style="white")

    table.add_row("/mode vector", "Gunakan Vector Retrieval (cosine similarity)")
    table.add_row("/mode graph", "Gunakan Graph Retrieval (relasional)")
    table.add_row("/mode compare", "Bandingkan kedua mode sekaligus")
    table.add_row("/provider", "Ganti provider & model LLM (runtime)")
    table.add_row("/info", "Tampilkan provider, model, dan mode saat ini")
    table.add_row("/hotspots", "Tampilkan 10 file paling sering diubah")
    table.add_row("/help", "Tampilkan bantuan ini")
    table.add_row("/q, /quit", "Keluar dari Joomha")

    console.print(table)


def show_mode_change(mode: str) -> None:
    """Confirm a mode switch to the user."""
    color = MODE_COLORS.get(mode, "white")
    console.print(f"[{color}]\u2713 Mode diubah ke: {mode}[/{color}]")


def show_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold red]\u2717 Error:[/bold red] {message}")


def show_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[bold blue]\u2139[/bold blue] {message}")

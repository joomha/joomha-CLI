"""Input handler — prompt-toolkit session with slash-command completion."""

from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

SLASH_COMMANDS = [
    "/mode",
    "/mode vector",
    "/mode graph",
    "/mode compare",
    "/hotspots",
    "/provider",
    "/info",
    "/help",
    "/q",
    "/quit",
]


def create_session(history_path: str) -> PromptSession:
    """Create a PromptSession with auto-complete, history, and auto-suggest."""
    Path(history_path).parent.mkdir(parents=True, exist_ok=True)

    completer = WordCompleter(SLASH_COMMANDS, sentence=True)

    session: PromptSession = PromptSession(
        completer=completer,
        history=FileHistory(history_path),
        auto_suggest=AutoSuggestFromHistory(),
    )
    return session

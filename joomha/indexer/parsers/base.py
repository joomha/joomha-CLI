"""Base parser — abstract contract that all language parsers must implement."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict


class BaseParser(ABC):
    """Abstract base class defining the parser interface.

    Every language parser must implement:
      - parse_file()  → extract nodes and edges from a single file
      - extensions()  → return supported file extensions (e.g. [".py"])
      - language()    → return human-readable language name
    """

    @abstractmethod
    def parse_file(
        self, file_path: Path, repo_root: Path
    ) -> Dict[str, List[Dict]]:
        """Parse a single source file.

        Returns a dict with two keys:
            "nodes" → list of node dicts:
                {file_path, node_type, name, start_line, end_line, language}
            "edges" → list of edge dicts:
                {source_file, target_file, edge_type}
        """
        ...

    @abstractmethod
    def extensions(self) -> List[str]:
        """Return the list of file extensions this parser handles.

        Example: [".py"] for Python, [".js", ".jsx"] for JavaScript.
        """
        ...

    @abstractmethod
    def language(self) -> str:
        """Return the language identifier string.

        Example: "python", "javascript", "typescript"
        """
        ...

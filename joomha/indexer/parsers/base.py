"""[PENANDA]"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict


class BaseParser(ABC):
    """[PENANDA]"""


    @abstractmethod
    def parse_file(
        self, file_path: Path, repo_root: Path
    ) -> Dict[str, List[Dict]]:
        """[PENANDA]"""

        ...

    @abstractmethod
    def extensions(self) -> List[str]:
        """Kembalikan ekstensi file yang didukung"""

        ...

    @abstractmethod
    def language(self) -> str:
        """Ambil identifier nama bahasa"""

        ...

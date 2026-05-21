"""[PENANDA]"""


from typing import List, Dict

from sentence_transformers import SentenceTransformer
import lancedb

from joomha.config import EMBED_MODEL, TOP_K


class VectorRetriever:
    """Ambil kode berdasarkan kemiripan makna"""

    def __init__(self, lancedb_dir: str):
        self.model = SentenceTransformer(EMBED_MODEL)
        self.db = lancedb.connect(lancedb_dir)
        try:
            self.table = self.db.open_table("code_chunks")
        except Exception:
            self.table = None

    def retrieve(self, query: str) -> List[Dict]:
        """Cari potongan kode paling mirip dengan kueri"""
        if self.table is None:
            return []
            
        vec = self.model.encode(query).tolist()
        results = self.table.search(vec).limit(TOP_K).to_list()

        formatted: List[Dict] = []
        for r in results:
            formatted.append({
                "file_path":  r["file_path"],
                "start_line": r["start_line"],
                "end_line":   r["end_line"],
                "text":       r["text"],
                "score":      r.get("_distance", 0.0),
                "source":     "vector",
            })
        return formatted

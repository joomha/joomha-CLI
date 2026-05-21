"""[PENANDA]"""


import re
import sqlite3
from pathlib import Path
from typing import List, Dict, Set

from joomha.config import TOP_K


class GraphRetriever:
    """Ambil konteks dari relasi kode struktur"""

    def __init__(self, db_path: str, repo_root: str):
        self.db_path = db_path
        self.repo_root = Path(repo_root)

    # ------------------------------------------------------------------
    # Fungsi Internal Pembantu
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _extract_keywords(self, query: str) -> List[str]:
        """[PENANDA]"""

        keywords: List[str] = []

        # Nama file dengan ekstensi
        file_pattern = r'\b[\w.-]+\.(?:py|js|jsx|ts|tsx|mjs|cjs)\b'
        files_found = re.findall(file_pattern, query, re.IGNORECASE)
        keywords.extend(files_found)

        # Tambahkan nama file tanpa ekstensi untuk pencocokan
        for f in files_found:
            stem = Path(f).stem
            if stem and len(stem) >= 2:
                keywords.append(stem)

        # Identifier CamelCase dan snake_case
        pattern = r'\b[A-Z][a-zA-Z0-9]+\b|[a-z]+_[a-z_]+\b'
        keywords.extend(re.findall(pattern, query))

        # Fallback: ambil kata yang lebih dari 3 karakter
        stop_words = {
            "yang", "dari", "untuk", "dengan", "pada", "akan", "this",
            "that", "what", "where", "which", "there", "have", "file",
            "bagaimana", "jelaskan", "dimana", "fungsi", "kelas",
            "explain", "describe", "show", "find", "about",
        }
        if not keywords:
            words = re.findall(r'\b\w+\b', query)
            keywords = [w for w in words if len(w) > 3 and w.lower() not in stop_words]

        # Hilangkan duplikat, pertahankan urutan
        seen: set = set()
        unique: List[str] = []
        for kw in keywords:
            low = kw.lower()
            if low not in seen:
                seen.add(low)
                unique.append(kw)
        return unique

    def _find_nodes(self, keywords: List[str]) -> List[Dict]:
        """Cari node AST berdasarkan nama atau path file"""

        conn = self._get_conn()
        cursor = conn.cursor()
        nodes: List[Dict] = []
        seen: Set[tuple] = set()

        for kw in keywords:
            # Cari berdasarkan nama
            cursor.execute(
                "SELECT file_path, node_type, name, start_line, end_line "
                "FROM nodes WHERE name LIKE ? "
                "ORDER BY file_path, start_line",
                (f"%{kw}%",),
            )
            for row in cursor.fetchall():
                key = (row[0], row[2])
                if key not in seen:
                    seen.add(key)
                    nodes.append({
                        "file_path":  row[0],
                        "node_type":  row[1],
                        "name":       row[2],
                        "start_line": row[3],
                        "end_line":   row[4],
                    })

            # Cari berdasarkan path file
            cursor.execute(
                "SELECT file_path, node_type, name, start_line, end_line "
                "FROM nodes WHERE file_path LIKE ? "
                "ORDER BY start_line",
                (f"%{kw}%",),
            )
            for row in cursor.fetchall():
                key = (row[0], row[2])
                if key not in seen:
                    seen.add(key)
                    nodes.append({
                        "file_path":  row[0],
                        "node_type":  row[1],
                        "name":       row[2],
                        "start_line": row[3],
                        "end_line":   row[4],
                    })

        conn.close()
        return nodes

    def _get_import_neighbors(self, file_path: str) -> List[str]:
        """Ambil file yang terkait import"""

        conn = self._get_conn()
        cursor = conn.cursor()

        # Pencocokan teks persis
        cursor.execute(
            "SELECT source_file FROM edges "
            "WHERE target_file = ? AND edge_type='imports'",
            (file_path,),
        )
        results = [row[0] for row in cursor.fetchall()]

        cursor.execute(
            "SELECT target_file FROM edges "
            "WHERE source_file = ? AND edge_type='imports'",
            (file_path,),
        )
        results.extend(row[0] for row in cursor.fetchall())

        conn.close()
        return list(set(results))

    def _get_cochange_neighbors(self, file_path: str) -> List[Dict]:
        """Cari file yang sering berubah bersamaan"""

        conn = self._get_conn()
        cursor = conn.cursor()

        # Pencocokan teks persis
        cursor.execute(
            "SELECT file_b, score FROM co_changes WHERE file_a = ? "
            "UNION "
            "SELECT file_a, score FROM co_changes WHERE file_b = ?",
            (file_path, file_path),
        )
        raw_results = cursor.fetchall()

        # Normalisasi skor dengan metrik hotspot
        cursor.execute(
            "SELECT change_count FROM hotspots WHERE file_path = ?",
            (file_path,),
        )
        row = cursor.fetchone()
        changes_a = row[0] if row else None

        results: List[Dict] = []
        for partner_file, raw_score in raw_results:
            if changes_a is not None:
                cursor.execute(
                    "SELECT change_count FROM hotspots WHERE file_path = ?",
                    (partner_file,),
                )
                row_b = cursor.fetchone()
                changes_b = row_b[0] if row_b else None
                if changes_b is not None:
                    denominator = changes_a + changes_b - raw_score
                    norm_score = round(raw_score / denominator, 4) if denominator > 0 else 0
                else:
                    norm_score = raw_score
            else:
                norm_score = raw_score

            results.append({"file": partner_file, "score": norm_score})

        conn.close()
        return sorted(results, key=lambda x: x["score"], reverse=True)

    def _read_file_content(self, file_path: str, max_chars: int = 3000) -> str:
        """Baca sebagian karakter dari file"""
        full_path = self.repo_root / file_path
        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
            return content[:max_chars]
        except Exception:
            return ""

    def _get_global_metadata(self, query: str) -> str:
        """Deteksi analitik global dari Git"""
        q = query.lower()
        conn = self._get_conn()
        cursor = conn.cursor()
        
        try:
            # Deteksi kueri author paling aktif
            # Prioritaskan deteksi developer aktif
            if any(k in q for k in ["developer", "author", "kontributor", "pembuat", "siapa yang", "berkontribusi"]):
                cursor.execute("SELECT author, sum(changes) as total FROM ownership GROUP BY author ORDER BY total DESC LIMIT 10")
                rows = cursor.fetchall()
                if rows:
                    return "STATISTIK GIT (OWNERSHIP) - Kontributor Paling Aktif:\n" + "\n".join([f"- {r[0]} ({r[1]} total revisi)" for r in rows])
                    
            # Deteksi kueri file paling sering diubah
            if any(k in q for k in ["paling banyak diubah", "paling sering diubah", "di ubah", "hotspot", "sering diganti", "sering diedit", "sering di edit", "file mana"]):
                cursor.execute("SELECT file_path, change_count FROM hotspots ORDER BY change_count DESC LIMIT 10")
                rows = cursor.fetchall()
                if rows:
                    return "STATISTIK GIT (HOTSPOTS) - 10 File Paling Sering Diubah:\n" + "\n".join([f"- {r[0]} ({r[1]} revisi)" for r in rows])
                    
        except sqlite3.OperationalError:
            pass # Tabel mungkin belum dibuat
        finally:
            conn.close()
            
        return ""

    def retrieve(self, query: str) -> List[Dict]:
        """[PENANDA]"""

        results: List[Dict] = []
        
        # Injeksi metadata dari Git
        meta_text = self._get_global_metadata(query)
        if meta_text:
            results.append({
                "file_path":  "GLOBAL_GIT_STATISTICS",
                "text":       meta_text,
                "node_type":  "graph_analytics",
                "node_name":  "git_history",
                "start_line": 0,
                "end_line":   0,
                "importers":  [],
                "cochanges":  [],
                "source":     "graph_metadata",
            })

        keywords = self._extract_keywords(query)
        if not keywords and not meta_text:
            return []
            
        nodes = self._find_nodes(keywords)
        if not nodes and not meta_text:
            return []
            
        if not nodes and meta_text:
            return results

        # Gunakan jumlah limit yang bisa dikonfigurasi
        top_nodes = nodes[:TOP_K]
        seen_files: Set[str] = set()

        for node in top_nodes:
            fp = node["file_path"]
            if fp in seen_files:
                continue
            seen_files.add(fp)

            content = self._read_file_content(fp)
            importers = self._get_import_neighbors(fp)
            cochanges = self._get_cochange_neighbors(fp)

            results.append({
                "file_path":  fp,
                "text":       content,
                "node_type":  node["node_type"],
                "node_name":  node["name"],
                "start_line": node["start_line"],
                "end_line":   node["end_line"],
                "importers":  importers[:5],
                "cochanges":  cochanges[:5],
                "source":     "graph",
            })

        return results

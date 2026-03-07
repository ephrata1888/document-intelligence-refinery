import json
import os
import re
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

import chromadb
from models.extraction import NormalizedDocument
from models.page_index import PageIndex


class PageIndexNavigateTool:
    """Tool to navigate PageIndex files and find relevant sections."""

    def __init__(self, refinery_dir: Path = Path(".refinery")):
        self.refinery_dir = refinery_dir

    def search(self, query: str, doc_ids: List[str] = None) -> List[str]:
        """Return top-3 section IDs most relevant to the query."""
        if doc_ids is None:
            # Search all pageindex files
            pageindex_dir = self.refinery_dir / "pageindex"
            doc_ids = [f.stem for f in pageindex_dir.glob("*.json")]

        relevant_sections = []
        for doc_id in doc_ids:
            index_path = self.refinery_dir / "pageindex" / f"{doc_id}.json"
            if not index_path.exists():
                continue
            with open(index_path, "r") as f:
                index_data = json.load(f)
            root = PageIndex(**index_data)
            sections = self._find_sections(root, query)
            relevant_sections.extend(sections)

        # Sort by relevance score (assuming _find_sections returns tuples)
        relevant_sections.sort(key=lambda x: x[1], reverse=True)
        return [section for section, score in relevant_sections[:3]]

    def _find_sections(self, node: PageIndex, query: str) -> List[tuple[str, float]]:
        """Recursively find sections matching the query."""
        matches = []
        score = 0.0
        query_lower = query.lower()
        if query_lower in node.title.lower():
            score += 1.0
        if query_lower in node.summary.lower():
            score += 0.5
        if score > 0:
            matches.append((f"{node.title}_{node.page_range}", score))
        for child in node.child_sections:
            matches.extend(self._find_sections(child, query))
        return matches


class SemanticSearchTool:
    """Tool for semantic search in ChromaDB with section filtering."""

    def __init__(self, refinery_dir: Path = Path(".refinery")):
        self.refinery_dir = refinery_dir
        self.client = chromadb.PersistentClient(path=str(refinery_dir / "vectors"))
        self.collection = self.client.get_or_create_collection("documents")

    def search(self, query: str, selected_sections: List[str] = None, n_results: int = 5) -> List[str]:
        """Search ChromaDB, optionally filtered by sections."""
        where = None
        if selected_sections:
            # Filter by parent_section
            where = {"parent_section": {"$in": selected_sections}}

        results = self.collection.query(
            query_texts=[query],
            where=where,
            n_results=n_results
        )
        return results["documents"][0] if results["documents"] else []


class FactTableTool:
    """Tool for extracting and querying numerical facts from documents."""

    def __init__(self, refinery_dir: Path = Path(".refinery")):
        self.refinery_dir = refinery_dir
        self.db_path = refinery_dir / "fact_table.db"
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database with facts table."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                doc_id TEXT,
                key TEXT,
                value REAL,
                unit TEXT,
                page_number INTEGER,
                bbox TEXT,
                content_hash TEXT
            )
        """)
        conn.commit()
        conn.close()

    def extract_facts(self, doc: NormalizedDocument):
        """Extract numerical key-value pairs from document."""
        if doc is None:
            return
        conn = sqlite3.connect(self.db_path)
        facts = []
        for page in doc.pages:
            text = page.text
            # Simple regex for key: value patterns
            patterns = [
                r"(\w+):\s*([\d,]+\.?\d*)\s*(\w*)",
                r"(\w+)\s+is\s+([\d,]+\.?\d*)\s*(\w*)",
            ]
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    key, value_str, unit = match
                    try:
                        value = float(value_str.replace(",", ""))
                        bbox = f"{page.text_bbox.x0},{page.text_bbox.y0},{page.text_bbox.x1},{page.text_bbox.y1}" if page.text_bbox else ""
                        facts.append((
                            doc.doc_id, key, value, unit, getattr(page, 'page_no', 1), bbox, ""
                                                ))
                    except ValueError:
                        continue
        if facts:
            conn.executemany("INSERT INTO facts VALUES (?, ?, ?, ?, ?, ?, ?)", facts)
            conn.commit()
        conn.close()

    def query(self, sql: str) -> List[Dict[str, Any]]:
        """Execute SQL query on facts table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            results = [{"error": str(e)}]
        conn.close()
        return results
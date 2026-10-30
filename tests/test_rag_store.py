"""Unit tests for local vector indexing without requiring an Ollama daemon."""
from pathlib import Path
from unittest.mock import patch

from memory import rag_store


class _Document:
    def __init__(self, page_content, metadata):
        self.page_content = page_content
        self.metadata = metadata


class _Chunk:
    def __init__(self, text, start=0):
        self.page_content = text
        self.metadata = {"start_index": start}


class _Splitter:
    def __init__(self, **_kwargs):
        pass

    def split_documents(self, documents):
        text = documents[0].page_content
        return [_Chunk(text[:100], 0)]


class _Table:
    def __init__(self):
        self.rows = []

    def add(self, rows):
        self.rows.extend(rows)

    def search(self, _vector):
        table = self
        class Query:
            def limit(self, _limit):
                return self
            def to_list(self):
                return [{"text": row["text"], "source": row["source"], "_distance": 0.1}
                        for row in table.rows]
        return Query()

    def count_rows(self):
        return len(self.rows)


class _DB:
    def __init__(self):
        self.table = None

    def open_table(self, _name):
        if self.table is None:
            raise FileNotFoundError
        return self.table

    def create_table(self, _name, data):
        self.table = _Table()
        self.table.add(data)
        return self.table


class _LanceDB:
    def __init__(self):
        self.db = _DB()

    def connect(self, _path):
        return self.db


def test_index_text_uses_real_embedding_dimension_and_searches(tmp_path):
    fake_db = _LanceDB()
    dependencies = (fake_db, _Document, _Splitter)
    with (
        patch.object(rag_store, "_dependencies", return_value=dependencies),
        patch.object(rag_store, "_embed", return_value=[[0.1, 0.2, 0.3]]),
        patch.object(rag_store, "VECTOR_DB_PATH", tmp_path),
    ):
        result = rag_store.index_text("EDITH local knowledge", "test-note")
        assert result["chunks_indexed"] == 1
        assert len(fake_db.db.table.rows[0]["vector"]) == 3
        found = rag_store.search_knowledge("EDITH", limit=3)
        assert found[0]["source"] == "test-note"
        assert rag_store.knowledge_stats()["chunks"] == 1

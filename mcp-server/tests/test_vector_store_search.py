
from types import SimpleNamespace

import pytest

from retrieval import vector_store


def make_doc(
    document_id: str,
    owner_id: str,
    version: str,
    text: str,
    chunk_index: int = 0,
):
    return SimpleNamespace(
        page_content=text,
        metadata={
            "document_id": document_id,
            "owner_id": owner_id,
            "indexing_version": version,
            "filename": f"{document_id}.txt",
            "chunk_index": chunk_index,
        },
    )


def matches_filter(metadata: dict, condition: dict) -> bool:
    """Small evaluator for the Chroma filters used by search()."""
    for key, value in condition.items():
        if key == "$and":
            if not all(matches_filter(metadata, item) for item in value):
                return False
        elif key == "$or":
            if not any(matches_filter(metadata, item) for item in value):
                return False
        elif metadata.get(key) != value:
            return False

    return True


class FakeChromaStore:
    def __init__(self, docs_with_scores):
        self.docs_with_scores = docs_with_scores
        self.last_filter = None
        self.called = False

    def similarity_search_with_score(self, query, k, filter=None):
        self.called = True
        self.last_filter = filter

        matches = [
            (doc, score)
            for doc, score in self.docs_with_scores
            if matches_filter(doc.metadata, filter or {})
        ]

        matches.sort(key=lambda item: item[1])
        return matches[:k]


@pytest.fixture
def fake_store(monkeypatch):
    docs = [
        (
            make_doc(
                "doc-1", "user-1", "v1",
                "old document content"
            ),
            0.10,
        ),
        (
            make_doc(
                "doc-1", "user-1", "v2",
                "current document content"
            ),
            0.20,
        ),
        (
            make_doc(
                "doc-2", "user-1", "v1",
                "another current document"
            ),
            0.30,
        ),
        (
            make_doc(
                "doc-3", "user-2", "v1",
                "another user's secret"
            ),
            0.05,
        ),
    ]

    fake = FakeChromaStore(docs)
    monkeypatch.setattr(vector_store, "_store", fake)
    return fake


def test_empty_active_versions_returns_no_results(fake_store):
    results = vector_store.search(
        owner_id="user-1",
        query="document",
        k=4,
        active_versions={},
    )

    assert results == []
    assert fake_store.called is False


def test_only_active_version_is_returned(fake_store):
    results = vector_store.search(
        owner_id="user-1",
        query="document",
        k=4,
        active_versions={"doc-1": "v2"},
    )

    assert len(results) == 1
    assert results[0]["document_id"] == "doc-1"
    assert results[0]["indexing_version"] == "v2"


def test_multiple_documents_return_their_active_versions(fake_store):
    results = vector_store.search(
        owner_id="user-1",
        query="document",
        k=4,
        active_versions={
            "doc-1": "v2",
            "doc-2": "v1",
        },
    )

    returned_pairs = {
        (item["document_id"], item["indexing_version"])
        for item in results
    }

    assert returned_pairs == {
        ("doc-1", "v2"),
        ("doc-2", "v1"),
    }


def test_stale_version_is_excluded(fake_store):
    results = vector_store.search(
        owner_id="user-1",
        query="document",
        k=4,
        active_versions={"doc-1": "v2"},
    )

    assert all(
        item["indexing_version"] != "v1"
        for item in results
    )


def test_other_owners_chunks_are_excluded(fake_store):
    results = vector_store.search(
        owner_id="user-1",
        query="document",
        k=4,
        active_versions={
            "doc-1": "v2",
            "doc-2": "v1",
            "doc-3": "v1",
        },
    )

    assert all(item["owner_id"] == "user-1" for item in results)
    assert all(
        item["document_id"] != "doc-3"
        for item in results
    )


def test_k_limits_number_of_results(fake_store):
    results = vector_store.search(
        owner_id="user-1",
        query="document",
        k=1,
        active_versions={
            "doc-1": "v2",
            "doc-2": "v1",
        },
    )

    assert len(results) == 1

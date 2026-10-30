
import threading
from typing import Any, cast

import pytest

from retrieval import hybrid_search


def make_records(version: str) -> list[dict]:
    return [
        {
            "document_id": "doc_1",
            "indexing_version": version,
            "chunk_index": 0,
            "text": f"Employee leave policy for {version}",
            "filename": "leave_policy.txt",
        },
        {
            "document_id": "doc_1",
            "indexing_version": version,
            "chunk_index": 1,
            "text": f"Manager approval required for {version}",
            "filename": "leave_policy.txt",
        },
    ]


def setup_cache():
    hybrid_search.invalidate_all()


def test_get_index_builds_and_caches_index(monkeypatch):
    setup_cache()

    calls = []

    def fake_get_owner_chunks(owner_id, active_versions):
        calls.append((owner_id, active_versions))
        return make_records(active_versions["doc_1"])

    monkeypatch.setattr(
        hybrid_search.vector_store,
        "get_owner_chunks",
        fake_get_owner_chunks,
    )

    active_versions = {"doc_1": "version_1"}

    index1 = hybrid_search._get_index("user_1", active_versions)
    index2 = hybrid_search._get_index("user_1", active_versions)

    assert index1 is not None
    assert index1 is index2

    # Chunks should only be retrieved once because the second call uses cache.
    assert len(calls) == 1


def test_active_version_change_creates_new_index(monkeypatch):
    setup_cache()

    calls = []

    def fake_get_owner_chunks(owner_id, active_versions):
        calls.append(active_versions)
        return make_records(active_versions["doc_1"])

    monkeypatch.setattr(
        hybrid_search.vector_store,
        "get_owner_chunks",
        fake_get_owner_chunks,
    )

    index1 = hybrid_search._get_index(
        "user_1",
        {"doc_1": "version_1"},
    )

    index2 = hybrid_search._get_index(
        "user_1",
        {"doc_1": "version_2"},
    )

    assert index1 is not None
    assert index2 is not None

    # Different active versions must produce different cache entries.
    assert index1 is not index2
    assert len(calls) == 2

    assert index1.records[0]["indexing_version"] == "version_1"
    assert index2.records[0]["indexing_version"] == "version_2"


def test_invalidate_all_forces_rebuild(monkeypatch):
    setup_cache()

    calls = []

    def fake_get_owner_chunks(owner_id, active_versions):
        calls.append(owner_id)
        return make_records(active_versions["doc_1"])

    monkeypatch.setattr(
        hybrid_search.vector_store,
        "get_owner_chunks",
        fake_get_owner_chunks,
    )

    active_versions = {"doc_1": "version_1"}

    index1 = hybrid_search._get_index("user_1", active_versions)

    hybrid_search.invalidate_all()

    index2 = hybrid_search._get_index("user_1", active_versions)

    assert index1 is not None
    assert index2 is not None
    assert index1 is not index2

    # First build + rebuild after invalidation.
    assert len(calls) == 2


def test_empty_active_versions_returns_none(monkeypatch):
    setup_cache()

    def should_not_be_called(owner_id, active_versions):
        raise AssertionError("Should not retrieve chunks")

    monkeypatch.setattr(
        hybrid_search.vector_store,
        "get_owner_chunks",
        should_not_be_called,
    )

    result = hybrid_search._get_index("user_1", {})

    assert result is None


def test_no_records_returns_none(monkeypatch):
    setup_cache()

    def fake_get_owner_chunks(owner_id, active_versions):
        return []

    monkeypatch.setattr(
        hybrid_search.vector_store,
        "get_owner_chunks",
        fake_get_owner_chunks,
    )

    result = hybrid_search._get_index(
        "user_1",
        {"doc_1": "version_1"},
    )

    assert result is None


def test_records_without_tokens_returns_none(monkeypatch):
    setup_cache()

    def fake_get_owner_chunks(owner_id, active_versions):
        return [
            {
                "document_id": "doc_1",
                "indexing_version": "version_1",
                "chunk_index": 0,
                "text": "!!!",
                "filename": "empty.txt",
            }
        ]

    monkeypatch.setattr(
        hybrid_search.vector_store,
        "get_owner_chunks",
        fake_get_owner_chunks,
    )

    result = hybrid_search._get_index(
        "user_1",
        {"doc_1": "version_1"},
    )

    assert result is None



def test_generation_change_prevents_stale_index_from_being_cached(monkeypatch):
    setup_cache()

    build_started = threading.Event()
    allow_build_to_finish = threading.Event()

    def fake_get_owner_chunks(owner_id, active_versions):
        build_started.set()

        # Pause index construction until the test invalidates the cache.
        assert allow_build_to_finish.wait(timeout=5)

        return make_records(active_versions["doc_1"])

    monkeypatch.setattr(
        hybrid_search.vector_store,
        "get_owner_chunks",
        fake_get_owner_chunks,
    )

    result = {}

    def build_index():
        result["index"] = hybrid_search._get_index(
            "user_1",
            {"doc_1": "version_1"},
        )

    thread = threading.Thread(target=build_index)
    thread.start()

    # Wait until the index build has started.
    assert build_started.wait(timeout=5)

    # Simulate a document write or delete.
    hybrid_search.invalidate_all()

    # Allow the original build to continue.
    allow_build_to_finish.set()

    thread.join(timeout=5)

    assert not thread.is_alive()
    assert result["index"] is not None

    # The old build should not have been cached.
    assert hybrid_search._cache == {}



def test_bm25_search_respects_limit(monkeypatch):
    hybrid_search.invalidate_all()

    records = [
        {
            "document_id": "doc_1",
            "indexing_version": "version_1",
            "chunk_index": 0,
            "text": "employee leave policy",
            "filename": "leave.txt",
        },
        {
            "document_id": "doc_1",
            "indexing_version": "version_1",
            "chunk_index": 1,
            "text": "employee leave policy approval",
            "filename": "leave.txt",
        },
        {
            "document_id": "doc_1",
            "indexing_version": "version_1",
            "chunk_index": 2,
            "text": "employee leave policy manager",
            "filename": "leave.txt",
        },
        {
            "document_id": "doc_1",
            "indexing_version": "version_1",
            "chunk_index": 3,
            "text": "unrelated content",
            "filename": "leave.txt",
        },
    ]

    def fake_get_owner_chunks(owner_id, active_versions):
        return records

    monkeypatch.setattr(
        hybrid_search.vector_store,
        "get_owner_chunks",
        fake_get_owner_chunks,
    )

    results = hybrid_search._bm25_search(
        owner_id="user_1",
        query="employee leave policy",
        limit=2,
        active_versions={"doc_1": "version_1"},
    )

    assert len(results) <= 2



def test_deduplicate_hits_removes_duplicate_chunks():
    chunk_a = {
        "document_id": "doc_1",
        "indexing_version": "version_1",
        "chunk_index": 0,
        "text": "Annual leave policy",
    }

    chunk_b = {
        "document_id": "doc_1",
        "indexing_version": "version_1",
        "chunk_index": 1,
        "text": "Leave approval process",
    }

    hits = [chunk_a, chunk_a, chunk_b, chunk_a]

    result = hybrid_search._deduplicate_hits(hits)

    assert len(result) == 2
    assert result[0] is chunk_a
    assert result[1] is chunk_b


def test_hybrid_search_fuses_dense_and_bm25(monkeypatch):
    hybrid_search.invalidate_all()

    chunk_a = {
        "document_id": "doc_1",
        "indexing_version": "version_1",
        "chunk_index": 0,
        "text": "Annual leave policy",
        "filename": "leave.txt",
    }

    chunk_b = {
        "document_id": "doc_1",
        "indexing_version": "version_1",
        "chunk_index": 1,
        "text": "Leave approval process",
        "filename": "leave.txt",
    }

    chunk_c = {
        "document_id": "doc_2",
        "indexing_version": "version_1",
        "chunk_index": 0,
        "text": "Remote work policy",
        "filename": "remote.txt",
    }

    # Dense ranks: A = 1, B = 2
    monkeypatch.setattr(
        hybrid_search.vector_store,
        "search",
        lambda *args, **kwargs: [chunk_a, chunk_b],
    )

    # BM25 ranks: B = 1, C = 2
    monkeypatch.setattr(
        hybrid_search,
        "_bm25_search",
        lambda *args, **kwargs: [chunk_b, chunk_c],
    )

    results = hybrid_search.search(
        owner_id="user_1",
        query="leave policy",
        k=3,
        mode="hybrid",
        active_versions={"doc_1": "version_1", "doc_2": "version_1"},
    )

    by_chunk = {
        (hit["document_id"], hit["chunk_index"]): hit
        for hit in results
    }

    # B is returned by both retrievers but must appear only once.
    assert len(results) == 3
    assert len(by_chunk) == 3

    # B: dense rank 2 + BM25 rank 1
    expected_b_score = 1 / (60 + 2) + 1 / (60 + 1)
    assert abs(by_chunk[("doc_1", 1)]["score"] - expected_b_score) < 1e-9
    assert by_chunk[("doc_1", 1)]["dense_rank"] == 2
    assert by_chunk[("doc_1", 1)]["bm25_rank"] == 1

    # The indexing version must be preserved in the fused output.
    assert by_chunk[("doc_1", 1)]["indexing_version"] == "version_1"

    # B should rank above A and C.
    assert results[0]["document_id"] == "doc_1"
    assert results[0]["chunk_index"] == 1


def test_hybrid_search_respects_k(monkeypatch):
    hybrid_search.invalidate_all()

    chunks = [
        {
            "document_id": f"doc_{i}",
            "indexing_version": "version_1",
            "chunk_index": 0,
            "text": f"Policy {i}",
            "filename": f"doc_{i}.txt",
        }
        for i in range(4)
    ]

    monkeypatch.setattr(
        hybrid_search.vector_store,
        "search",
        lambda *args, **kwargs: chunks,
    )

    monkeypatch.setattr(
        hybrid_search,
        "_bm25_search",
        lambda *args, **kwargs: [],
    )

    results = hybrid_search.search(
        owner_id="user_1",
        query="policy",
        k=2,
        mode="hybrid",
        active_versions={
            f"doc_{i}": "version_1"
            for i in range(4)
        },
    )

    assert len(results) == 2


from retrieval import hybrid_search


def test_rrf_combines_rankings_correctly(monkeypatch):
    hybrid_search.invalidate_all()

    chunk_a = {
        "document_id": "doc-a",
        "indexing_version": "v1",
        "chunk_index": 0,
        "text": "Content A",
        "filename": "a.txt",
    }
    chunk_b = {
        "document_id": "doc-b",
        "indexing_version": "v1",
        "chunk_index": 0,
        "text": "Content B",
        "filename": "b.txt",
    }
    chunk_c = {
        "document_id": "doc-c",
        "indexing_version": "v1",
        "chunk_index": 0,
        "text": "Content C",
        "filename": "c.txt",
    }

    # Dense ranks: A first, B second, C third.
    monkeypatch.setattr(
        hybrid_search.vector_store,
        "search",
        lambda *args, **kwargs: [chunk_a, chunk_b, chunk_c],
    )

    # BM25 ranks: B first, C second, A third.
    monkeypatch.setattr(
        hybrid_search,
        "_bm25_search",
        lambda *args, **kwargs: [chunk_b, chunk_c, chunk_a],
    )

    results = hybrid_search.search(
        owner_id="user-1",
        query="test query",
        k=3,
        mode="hybrid",
        active_versions={
            "doc-a": "v1",
            "doc-b": "v1",
            "doc-c": "v1",
        },
    )

    actual_order = [hit["document_id"] for hit in results]

    # B wins because it ranks highly in both retrievers.
    assert actual_order == ["doc-b", "doc-a", "doc-c"]

    scores = {
    hit["document_id"]: hit["score"]
    for hit in results
}

    assert scores["doc-b"] == pytest.approx(
    1 / 62 + 1 / 61
)

    assert scores["doc-a"] == pytest.approx(
    1 / 61 + 1 / 63
)

    assert scores["doc-c"] == pytest.approx(
    1 / 63 + 1 / 62
)




def test_deduplicate_hits_preserves_first_occurrence():
    chunk_a = {
        "document_id": "doc-a",
        "indexing_version": "v1",
        "chunk_index": 0,
        "text": "Content A",
        "filename": "a.txt",
    }

    duplicate_a = {
        **chunk_a,
        "text": "Duplicate copy of Content A",
    }

    chunk_b = {
        "document_id": "doc-b",
        "indexing_version": "v1",
        "chunk_index": 0,
        "text": "Content B",
        "filename": "b.txt",
    }

    results = hybrid_search._deduplicate_hits(
        [chunk_a, duplicate_a, chunk_b]
    )

    assert len(results) == 2
    assert [hit["document_id"] for hit in results] == [
        "doc-a",
        "doc-b",
    ]

    # The first occurrence should be preserved.
    assert results[0]["text"] == "Content A"


def test_hybrid_search_includes_chunks_found_by_only_one_retriever(
    monkeypatch,
):
    hybrid_search.invalidate_all()

    dense_only = {
        "document_id": "doc-a",
        "indexing_version": "v1",
        "chunk_index": 0,
        "text": "Semantically related content",
        "filename": "a.txt",
    }

    bm25_only = {
        "document_id": "doc-b",
        "indexing_version": "v1",
        "chunk_index": 0,
        "text": "Exact keyword match",
        "filename": "b.txt",
    }

    monkeypatch.setattr(
        hybrid_search.vector_store,
        "search",
        lambda *args, **kwargs: [dense_only],
    )

    monkeypatch.setattr(
        hybrid_search,
        "_bm25_search",
        lambda *args, **kwargs: [bm25_only],
    )

    results = hybrid_search.search(
        owner_id="user-1",
        query="leave policy",
        k=2,
        mode="hybrid",
        active_versions={
            "doc-a": "v1",
            "doc-b": "v1",
        },
    )

    results_by_id = {
        hit["document_id"]: hit
        for hit in results
    }

    assert set(results_by_id) == {"doc-a", "doc-b"}

    assert results_by_id["doc-a"]["dense_rank"] == 1
    assert results_by_id["doc-a"]["bm25_rank"] is None

    assert results_by_id["doc-b"]["dense_rank"] is None
    assert results_by_id["doc-b"]["bm25_rank"] == 1

    assert results_by_id["doc-a"]["score"] == pytest.approx(1 / 61)
    assert results_by_id["doc-b"]["score"] == pytest.approx(1 / 61)




def test_bm25_cache_evicts_least_recently_used_entry(monkeypatch):
    hybrid_search.invalidate_all()

    # Return one valid chunk for every owner so _get_index()
    # builds a real BM25 index through the production code.
    def fake_get_owner_chunks(owner_id, active_versions):
        return [
            {
                "document_id": "doc-1",
                "indexing_version": "v1",
                "chunk_index": 0,
                "text": f"policy content for {owner_id}",
                "filename": "doc-1.txt",
            }
        ]

    monkeypatch.setattr(
        hybrid_search.vector_store,
        "get_owner_chunks",
        fake_get_owner_chunks,
    )

    active_versions = {"doc-1": "v1"}

    try:
        # Populate the cache through the real _get_index().
        for i in range(hybrid_search._MAX_CACHED_INDEXES):
            index = hybrid_search._get_index(
                f"user-{i}",
                active_versions,
            )
            assert index is not None

        assert len(hybrid_search._cache) == 64

        oldest_key = next(iter(hybrid_search._cache))

        # Access the second entry so it becomes recently used.
        recently_used_key = (
            "user-1",
            (("doc-1", "v1"),),
        )
        hybrid_search._get_index("user-1", active_versions)

        # Add one more owner through the real index builder.
        hybrid_search._get_index("user-new", active_versions)

        assert len(hybrid_search._cache) == 64
        assert oldest_key not in hybrid_search._cache
        assert recently_used_key in hybrid_search._cache
        assert (
            "user-new",
            (("doc-1", "v1"),),
        ) in hybrid_search._cache

    finally:
        hybrid_search.invalidate_all()

import uuid
import pytest
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import FakeEmbeddings
from retrieval import hybrid_search, vector_store


def make_document(
    document_id: str,
    owner_id: str,
    version_id: str,
    text: str,
    chunk_index: int = 0,
) -> Document:
    return Document(
        page_content=text,
        metadata={
            "document_id": document_id,
            "owner_id": owner_id,
            "indexing_version": version_id,
            "filename": f"{document_id}.txt",
            "chunk_index": chunk_index,
        },
    )


def test_hybrid_search_with_real_chroma_and_bm25(
    tmp_path,
    monkeypatch,
):
    store = Chroma(
        collection_name=f"test_{uuid.uuid4().hex}",
        embedding_function=FakeEmbeddings(size=32),
        persist_directory=str(tmp_path / "chroma"),
    )

    original_store = vector_store._store

    try:
        documents = [
            make_document(
                "doc-1", "user-1", "v1",
                "obsolete leave policy old entitlement",
            ),
            make_document(
                "doc-1", "user-1", "v2",
                "annual leave entitlement employees vacation days",
            ),
            make_document(
                "doc-1", "user-1", "v2",
                "leave approval manager approval workflow",
                chunk_index=1,
            ),
            make_document(
                "doc-2", "user-1", "v1",
                "remote work policy home office",
            ),
            make_document(
                "doc-3", "user-2", "v1",
                "private employee leave records",
            ),
        ]

        store.add_documents(
            documents=documents,
            ids=[
                "doc-1:v1:0",
                "doc-1:v2:0",
                "doc-1:v2:1",
                "doc-2:v1:0",
                "doc-3:v1:0",
            ],
        )

        monkeypatch.setattr(vector_store, "_store", store)

        active_versions = {
            "doc-1": "v2",
            "doc-2": "v1",
        }

        # Ensure the test starts without an old BM25 cache entry.
        hybrid_search.invalidate_all()

        results = hybrid_search.search(
            owner_id="user-1",
            query="annual leave entitlement",
            k=10,
            mode="hybrid",
            active_versions=active_versions,
        )

        assert results, "Hybrid search should return results."

        # Each chunk should appear at most once in the fused output.
        keys = [
            (
                hit["document_id"],
                hit["indexing_version"],
                hit["chunk_index"],
            )
            for hit in results
        ]
        assert len(keys) == len(set(keys))

        # All results must belong to the active versions of user-1.
        assert all(
            hit["indexing_version"]
            == active_versions[hit["document_id"]]
            for hit in results
        )

        assert all(
            hit["document_id"] in active_versions
            for hit in results
        )

        # The returned fused results should preserve version metadata.
        assert all(
            "indexing_version" in hit
            for hit in results
        )

        # Hybrid mode should provide rank metadata from at least one
        # retriever for each result.
        assert all(
            hit["dense_rank"] is not None
            or hit["bm25_rank"] is not None
            for hit in results
        )
        # Verify that RRF scores match the recorded retriever ranks.
        for hit in results:
           expected_score = 0.0

           if hit["dense_rank"] is not None:
               expected_score += 1 / (
                  hybrid_search.RRF_K + hit["dense_rank"]
            )

           if hit["bm25_rank"] is not None:
               expected_score += 1 / (
                   hybrid_search.RRF_K + hit["bm25_rank"]
            )

           assert hit["score"] == pytest.approx(expected_score)

        # Verify that the BM25 index was built from the active chunks.
        index = hybrid_search._get_index(
            "user-1",
            active_versions,
        )

        assert index is not None
        assert all(
            record["indexing_version"]
            == active_versions[record["document_id"]]
            for record in index.records
        )

    finally:
        hybrid_search.invalidate_all()
        monkeypatch.setattr(vector_store, "_store", original_store)
        store.delete_collection()


import uuid

import pytest
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import FakeEmbeddings

from retrieval import hybrid_search, vector_store
from tests.retrieval_eval_cases import EVAL_CASES


def make_document(
    document_id,
    owner_id,
    version_id,
    text,
    chunk_index=0,
):
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


def reciprocal_rank(results, expected_chunks):
    for rank, hit in enumerate(results, start=1):
        key = (
            hit["document_id"],
            hit["indexing_version"],
            hit["chunk_index"],
        )

        if key in expected_chunks:
            return 1 / rank

    return 0.0


@pytest.mark.parametrize("case", EVAL_CASES)
def test_hybrid_retrieval_finds_expected_chunks(
    case,
    tmp_path,
    monkeypatch,
):
    store = Chroma(
        collection_name=f"eval_{uuid.uuid4().hex}",
        embedding_function=FakeEmbeddings(size=32),
        persist_directory=str(tmp_path / "eval_chroma"),
    )

    original_store = vector_store._store

    try:
        documents = [
            make_document(
                "doc-1",
                "user-1",
                "v1",
                "obsolete leave policy old entitlement",
            ),
            make_document(
                "doc-1",
                "user-1",
                "v2",
                "annual leave entitlement employees vacation days",
            ),
            make_document(
                "doc-1",
                "user-1",
                "v2",
                "leave approval manager approval workflow",
                chunk_index=1,
            ),
            make_document(
                "doc-2",
                "user-1",
                "v1",
                "remote work policy home office",
            ),
            make_document(
                "doc-3",
                "user-2",
                "v1",
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
        hybrid_search.invalidate_all()

        results = hybrid_search.search(
            owner_id=case["owner_id"],
            query=case["query"],
            k=3,
            mode="hybrid",
            active_versions=case["active_versions"],
        )

        expected_chunks = set(case["expected_chunks"])

        retrieved_chunks = {
            (
                hit["document_id"],
                hit["indexing_version"],
                hit["chunk_index"],
            )
            for hit in results
        }

        recall_at_3 = (
            len(expected_chunks & retrieved_chunks)
            / len(expected_chunks)
        )

        mrr = reciprocal_rank(results, expected_chunks)

        print(f"\nQuery: {case['query']}")
        print(f"Recall@3: {recall_at_3:.2f}")
        print(f"MRR: {mrr:.2f}")
        print(f"Retrieved chunks: {retrieved_chunks}")

        assert recall_at_3 == 1.0, (
            f"Expected chunks not found for query: {case['query']}"
        )

    finally:
        hybrid_search.invalidate_all()
        monkeypatch.setattr(vector_store, "_store", original_store)
        store.delete_collection()

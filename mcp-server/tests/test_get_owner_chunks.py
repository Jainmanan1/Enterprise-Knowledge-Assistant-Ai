import pytest
from langchain_chroma import Chroma
from langchain_core.embeddings import FakeEmbeddings

from retrieval import vector_store


@pytest.fixture
def real_chroma_store(tmp_path, monkeypatch):
    """Create an isolated, real Chroma collection for testing."""

    store = Chroma(
        collection_name="test_get_owner_chunks",
        embedding_function=FakeEmbeddings(size=32),
        persist_directory=str(tmp_path / "chroma_db"),
    )

    store.add_texts(
        texts=[
            "Old content from document one",
            "Updated content from document one",
            "Active content from document two",
            "Content belonging to another owner",
        ],
        metadatas=[
            {
                "owner_id": "user-1",
                "document_id": "doc-1",
                "filename": "doc1.txt",
                "chunk_index": 0,
                "indexing_version": "v1",
            },
            {
                "owner_id": "user-1",
                "document_id": "doc-1",
                "filename": "doc1.txt",
                "chunk_index": 0,
                "indexing_version": "v2",
            },
            {
                "owner_id": "user-1",
                "document_id": "doc-2",
                "filename": "doc2.txt",
                "chunk_index": 0,
                "indexing_version": "v1",
            },
            {
                "owner_id": "user-2",
                "document_id": "doc-3",
                "filename": "doc3.txt",
                "chunk_index": 0,
                "indexing_version": "v1",
            },
        ],
        ids=[
            "chunk-doc1-v1",
            "chunk-doc1-v2",
            "chunk-doc2-v1",
            "chunk-doc3-v1",
        ],
    )

    monkeypatch.setattr(vector_store, "_store", store)

    yield store

    store.delete_collection()


def test_empty_active_versions_returns_no_chunks(real_chroma_store):
    result = vector_store.get_owner_chunks(
        owner_id="user-1",
        active_versions={},
    )

    assert result == []


def test_get_owner_chunks_returns_only_active_versions(real_chroma_store):
    active_versions = {
        "doc-1": "v2",
        "doc-2": "v1",
    }

    result = vector_store.get_owner_chunks(
        owner_id="user-1",
        active_versions=active_versions,
    )

    result_pairs = {
        (chunk["document_id"], chunk["indexing_version"])
        for chunk in result
    }

    assert result_pairs == {
        ("doc-1", "v2"),
        ("doc-2", "v1"),
    }


def test_stale_version_is_excluded(real_chroma_store):
    result = vector_store.get_owner_chunks(
        owner_id="user-1",
        active_versions={"doc-1": "v2"},
    )

    versions = {
        chunk["indexing_version"]
        for chunk in result
    }

    assert versions == {"v2"}


def test_other_owners_chunks_are_excluded(real_chroma_store):
    result = vector_store.get_owner_chunks(
        owner_id="user-1",
        active_versions={
            "doc-1": "v2",
            "doc-2": "v1",
            "doc-3": "v1",
        },
    )

    owners = {
        chunk["owner_id"]
        for chunk in result
    }

    assert owners == {"user-1"}
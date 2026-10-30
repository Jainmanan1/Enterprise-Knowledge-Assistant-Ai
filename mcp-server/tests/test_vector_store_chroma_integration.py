
import uuid

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import FakeEmbeddings

from retrieval import vector_store


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


def test_chroma_search_filters_active_versions_and_owners(
    tmp_path,
    monkeypatch,
):
    # Create an isolated, temporary Chroma database.
    store = Chroma(
        collection_name=f"test_{uuid.uuid4().hex}",
        embedding_function=FakeEmbeddings(size=32),
        persist_directory=str(tmp_path / "chroma"),
    )

    try:
        documents = [
            make_document(
                "doc-1", "user-1", "v1",
                "This is the stale version of document one.",
            ),
            make_document(
                "doc-1", "user-1", "v2",
                "This is the active version of document one.",
            ),
            make_document(
                "doc-2", "user-1", "v1",
                "This is the active version of document two.",
            ),
            make_document(
                "doc-3", "user-2", "v1",
                "This is private content belonging to another user.",
            ),
        ]

        store.add_documents(
            documents=documents,
            ids=[
                "doc-1:v1:0",
                "doc-1:v2:0",
                "doc-2:v1:0",
                "doc-3:v1:0",
            ],
        )

        # Replace the production store only within this test.
        monkeypatch.setattr(vector_store, "_store", store)

        results = vector_store.search(
            owner_id="user-1",
            query="document content",
            k=10,
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

        # Old versions must never appear in the results.
        assert all(
            item["indexing_version"] != "v1"
            for item in results
            if item["document_id"] == "doc-1"
        )

        # No other owner's content may appear.
        assert all(
            item["owner_id"] == "user-1"
            for item in results
        )

    finally:
        store.delete_collection()

import os
import logging
import time
from typing import cast
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from chromadb.api.types import Where
logger = logging.getLogger(__name__)
CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db")
_embeddings : OllamaEmbeddings|None = None
_store: Chroma|None = None

def _get_embeddings() -> OllamaEmbeddings:
    """Create the embedding client only when it is needed."""
    global _embeddings

    if _embeddings is None:
        _embeddings = OllamaEmbeddings(model="nomic-embed-text")

    return _embeddings

def _get_store() -> Chroma:
    """Create the persistent Chroma store only when an operation needs it."""
    global _store

    if _store is None:
        _store = Chroma(
            collection_name="enterprise_docs",
            embedding_function=_get_embeddings(),
            persist_directory=CHROMA_DIR,
        )

    return _store

def _delete_with_retry(
        ids: list[str],max_retries:int=3
)-> None:
    if not ids:
        return
    store = _get_store()
    for attempt in range(1, max_retries + 1):
        try:
            store.delete(ids=ids)
            logger.info("Deleted %d chunks from Chorma", len(ids))
            return
        except Exception:
            logger.exception(
                "Attempt %d/%d to delete %d chunks from Chroma failed",
                attempt,
                max_retries,
                len(ids)
            )
            if attempt == max_retries:
                raise
            time.sleep(2 ** (attempt -1))  # Exponential backoff: 1s, 2s, 4s, etc.

def warm_up()-> None:
    t0 = time.perf_counter()
    _get_embeddings().embed_query("warm_up")
    logger.info("Embedding model ready in %.2fs", time.perf_counter() - t0)

def _matching_ids(*clauses: Where) -> list[str]:
    if not clauses:
        raise ValueError("At least one filter clause is required")
    where: Where = (
        clauses[0]
        if len(clauses) == 1
        else cast(Where, {"$and": list(clauses)})
    )
    return _get_store().get(where=where)["ids"]

def get_document_owner(document_id:str) ->str|None:
    store = _get_store()
    records = store.get(where={"document_id":document_id},include=["metadatas"])
    owners = {
        metadata.get("owner_id")
        for metadata in records["metadatas"]
        if metadata and metadata.get("owner_id")
    }

    if len(owners) > 1:
        raise RuntimeError(
            "Document has inconsistent owner metadata"
        )

    return next(iter(owners), None)

def index_chunks(owner_id:str,document_id:str,filename:str,chunks:list[str],version_id:str) ->int:

    docs =[
        Document(
            page_content = text,
            metadata = {
                "owner_id": owner_id,
                "document_id": document_id,
                "filename": filename,
                "chunk_index": i,
                "indexing_version": version_id,
            },


        )
        for i,text in enumerate(chunks)
        if text.strip()

    ]
    if not docs:
        raise ValueError("Cannot index a document with no text chunks")

    existing_owner  = get_document_owner(document_id)
    if existing_owner is not None and existing_owner != owner_id:
        raise PermissionError("Document belongs to another owner")

    # Give each version unique chunk IDs.
    ids = [
        f"{document_id}:{version_id}:{i}"
        for i in range(len(docs))
    ]
    batch_size = 16
    store = _get_store()

    try:
        for start in range(0, len(docs), batch_size):
            end = min(start + batch_size, len(docs))

            store.add_documents(
                documents = docs[start:end],
                ids=ids[start:end],
            )

            logger.info(
                "Indexed %d/%d chunks of %s",
                end,
                len(docs),
                document_id,
            )

    except Exception:
        logger.exception(
            "Indexing failed for document %s.  cleaning up new version.",
            document_id,
        )

        try:
            partial = _matching_ids(
                {"owner_id": owner_id}, {"document_id": document_id}, {"indexing_version": version_id}
            )
            if partial:
                _get_store().delete(ids=partial)
        except Exception:
            logger.exception("Could not clean partial version %s; reconciliation needed", version_id)
        raise

    return len(docs)

def search (
        owner_id:str,query:str,k:int,active_versions:dict[str,str]
) -> list[dict]:
    if not active_versions:
        return []

    version_filters =[
        {
        "$and":[
            {"document_id": document_id},
            {"indexing_version": version_id}
        ]
    }
    for document_id,version_id in active_versions.items()

    ]
    if len(version_filters) == 1:
        version_filters = version_filters[0]
    else:
        version_filters = {"$or": version_filters}

    # Enforce both ownership and active-version filtering.
    where: Where = cast(
        Where,
        {
            "$and": [
                {"owner_id": owner_id},
                 version_filters
            ]
        },
    )
    results = _get_store().similarity_search_with_score(
        query,
        k=k,
        filter=cast(dict[str, str], where),

    )
    return [
        {
            "text": doc.page_content,
            "filename": doc.metadata.get("filename"),
            "document_id": doc.metadata.get("document_id"),
            "owner_id": doc.metadata.get("owner_id"),
            "chunk_index": doc.metadata.get("chunk_index"),
            "indexing_version": doc.metadata.get("indexing_version"),
            "distance": float(score),  # lower = closer
        }
        for doc, score in results
    ]

def get_owner_chunks(owner_id: str,active_versions:dict[str,str]) -> list[dict]:
    """Return only the owner's chunks from active document versions."""

    if not active_versions:
        return []
    version_filters = [
        {
            "$and": [
                {"document_id": document_id},
                {"indexing_version": version_id},
            ]
        }
        for document_id, version_id in active_versions.items()
    ]
    if len(version_filters) == 1:
        version_filters = version_filters[0]
    else:
        version_filters = {"$or": version_filters}


    where: Where = cast(
        Where,
        {
            "$and": [
                {"owner_id": owner_id},
             version_filters
            ]
        },
    )
    data = _get_store().get(where=cast(dict,where), include=["documents", "metadatas"])
    results = []

    for text, meta in zip(data["documents"], data["metadatas"]):
        if text is None or meta is None:
            continue

        results.append(
            {
                "text": text,
                "filename": meta.get("filename"),
                "document_id": meta.get("document_id"),
                "owner_id": meta.get("owner_id"),
                "chunk_index": meta.get("chunk_index"),
                "indexing_version": meta.get("indexing_version"),
            }
        )

    return results

def delete_document(document_id: str) -> int:
    store = _get_store()
    existing = store.get(where={"document_id": document_id})
    ids = existing["ids"]
    if ids:
        _delete_with_retry(ids=ids)
    return len(ids)




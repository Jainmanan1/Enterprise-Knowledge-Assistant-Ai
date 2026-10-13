import os
import logging
import time
import uuid

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings

logger = logging.getLogger(__name__)

CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db")
_embeddings = OllamaEmbeddings(model="nomic-embed-text")
_store = Chroma(
    collection_name="enterprise_docs",
    embedding_function = _embeddings,
    persist_directory=CHROMA_DIR

)

def warm_up()-> None:
    t0 = time.perf_counter()
    _embeddings.embed_query("warm_up")
    logger.info("Embedding model ready in %.2fs", time.perf_counter() - t0)


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
    
    # Capture the currently indexed chunks before starting.
    old_records  = _store.get(where={"document_id": document_id})
    old_ids = old_records["ids"]
    
    # Give each version unique chunk IDs.
    ids = [
        f"{document_id}:{version_id}:{i}"
        for i in range(len(docs))
    ]
    batch_size = 16

    try:
        for start in range(0, len(docs), batch_size):
            end = min(start + batch_size, len(docs))

            _store.add_documents(
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
            new_records = _store.get(where = {"indexing_version": version_id})
            new_ids = new_records["ids"]
            if new_ids:
                _store.delete(ids=new_ids)
        except Exception:
            logger.exception(
                "Failed to clean up partial version%s. "
                "Manual or scheduled reconciliation may be needed.",
                version_id,
            )

        raise    

    # Phase 2: New indexing succeeded. Remove the old version.
    if old_ids:
        try:
            _store.delete(ids=old_ids)
        except Exception:
            logger.exception(
                "New version indexed, but old chunks could not "
                "be fully removed for document %s",
                document_id,
            )
        raise RuntimeError(
            f"New indexing succeeded, but stale chunks "
            f"could not be removed for document {document_id}"
        )   

    return len(docs)  



def search (
        owner_id:str,query:str,k:int
) -> list[dict]:
    results = _store.similarity_search_with_score(
        query,
        k=k,
        filter = {"owner_id": owner_id}

    )
    return [
        {
            "text": doc.page_content,
            "filename": doc.metadata.get("filename"),
            "document_id": doc.metadata.get("document_id"),
            "owner_id": doc.metadata.get("owner_id"),
            "chunk_index": doc.metadata.get("chunk_index"),
            "distance": float(score),  # lower = closer
        }
        for doc, score in results
    ]



def delete_document(document_id: str) -> int:
    existing = _store.get(where={"document_id": document_id})
    ids = existing["ids"]
    if ids:
        _store.delete(ids=ids)
    return len(ids)
    
def get_document_owner(document_id:str) ->str|None:
    records = _store.get(where={"document_id":document_id},include=["metadatas"])
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

    
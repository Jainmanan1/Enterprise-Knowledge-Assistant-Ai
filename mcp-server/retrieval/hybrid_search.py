import re
import threading
from dataclasses import dataclass
from collections import OrderedDict
from rank_bm25 import BM25Okapi
import logging
from retrieval import vector_store

RRF_K = 60

_Token = re.compile(r"\w+")

def _tokenize(text:str) -> list[str]:
    return _Token.findall(text.lower())

def _key(hit:dict) ->tuple[str,str,int]:
     return (
        hit["document_id"],
        hit["indexing_version"],
        hit["chunk_index"],
    )


def _deduplicate_hits(hits: list[dict]) -> list[dict]:
    unique_hits = []
    seen = set()

    for hit in hits:
        key = _key(hit)

        if key in seen:
            continue

        seen.add(key)
        unique_hits.append(hit)

    return unique_hits


@dataclass

class _OwnerIndex:
    bm25: BM25Okapi
    records:list[dict]


CacheKey = tuple[str,tuple[tuple[str,str],...]]
_MAX_CACHED_INDEXES = 64

_cache: OrderedDict[CacheKey, _OwnerIndex] = OrderedDict()

_generation = 0

_lock = threading.Lock()

def invalidate_all() -> None:
    """Call after ANY write (index or delete)."""
    global _generation
    with _lock:
        _cache.clear()
        _generation += 1


def _get_index(owner_id:str,active_versions:dict[str,str]) ->_OwnerIndex |None:
    if not active_versions:
        return None
    cache_key:CacheKey=(
        owner_id,
        tuple(sorted(active_versions.items()))
    )
    with _lock:
       cached = _cache.get(cache_key)

       if cached is not None:
           _cache.move_to_end(cache_key)
           return cached

       gen = _generation

    records = vector_store.get_owner_chunks(owner_id,active_versions)
    if not records:
        return None

    tokenized_records = [_tokenize(r["text"]) for r in records]
    #remove chunks that produce no return
    vaild_pairs = [
        (record,tokens) for record,tokens in zip(records,tokenized_records) if tokens
    ]

    if not vaild_pairs:
        return None

    valid_records=[
        record for record,_ in vaild_pairs
    ]

    tokenized_documents = [
        tokens for _,tokens in vaild_pairs
    ]

    bm25 = BM25Okapi(tokenized_documents)
    index = _OwnerIndex(bm25=bm25, records=valid_records)

    # Cache the index only if no invalidation occurred.
    with _lock:
       if gen == _generation:
           _cache[cache_key] = index
           _cache.move_to_end(cache_key)

           while len(_cache) > _MAX_CACHED_INDEXES:
               _cache.popitem(last=False)

       return index




def _bm25_search(owner_id:str,query:str,limit:int,active_versions:dict[str,str])->list[dict]:
    index = _get_index(owner_id,active_versions)
    tokens = _tokenize(query)
    if index is None or not tokens or limit<=0:
        return []
    scores = index.bm25.get_scores(tokens)
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    result = []
    for i in order:
        if scores[i] <=0:
            break
        result.append(index.records[i])
        if len(result) >= limit:
            break
    return result




def search(owner_id: str, query: str, k: int, mode: str = "hybrid", active_versions: dict[str, str] | None = None) -> list[dict]:
    active_versions = active_versions or {}
    pool = max(k * 4, 20)  # candidates taken from each retriever before fusing
    dense = vector_store.search(owner_id, query, pool, active_versions) if mode in ("hybrid", "dense") else []
    sparse = _bm25_search(owner_id, query, pool, active_versions) if mode in ("hybrid", "bm25") else []

    # Remove duplicate hits
    dense = _deduplicate_hits(dense)
    sparse = _deduplicate_hits(sparse)
    logging.info(
    "Hybrid search metadata check: dense_owner_ids=%s sparse_owner_ids=%s",
    [hit.get("owner_id") for hit in dense],
    [hit.get("owner_id") for hit in sparse],
)

    fused: dict[tuple[str, str, int], dict] = {}
    for source, hits in (("dense", dense), ("bm25", sparse)):
        for rank, hit in enumerate(hits, start=1):
            entry = fused.setdefault(_key(hit), {
                "text": hit["text"],
                "filename": hit["filename"],
                "document_id": hit["document_id"],
                "owner_id": hit.get("owner_id"),
                "chunk_index": hit["chunk_index"],
                "indexing_version": hit["indexing_version"],
                "score": 0.0,
                "dense_rank": None,
                "bm25_rank": None,

            })
            entry["score"] += 1.0 / (RRF_K + rank)
            entry[f"{source}_rank"] = rank

    return sorted(fused.values(), key=lambda e: e["score"], reverse=True)[:k]
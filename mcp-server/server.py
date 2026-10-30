import json
import logging
from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from typing import Literal, NoReturn
from retrieval import hybrid_search, vector_store
import os
from jose import jwt, JWTError
try:
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # fall back if this SDK version names it differently
    ToolError = PermissionError

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("knowledge-retrieval")
AUDIENCE = "knowledge-retrieval"
ISSUER = "enterprise-knowledge-assistant-backend"
MAX_CHUNKS = 2000
MAX_CHUNK_CHARS = 5000
MAX_ACTIVE_DOCS = 500  # one filter clause per document; Chroma filters have practical limits
_SECRET_VALUE = os.environ.get("MCP_TOKEN")
if not _SECRET_VALUE:
    raise RuntimeError("MCP_TOKEN is not set (shared signing secret with the backend)")
_SECRET: str = _SECRET_VALUE
mcp = MCPServer(
    name="knowledge-retrieval"
)

def _deny(tool: str, reason: str, **ctx) -> NoReturn:
    detail = " ".join(f"{k}={v}" for k, v in ctx.items())
    logger.warning("AUTH_DENIED tool=%s reason=%s %s", tool, reason, detail)
    raise ToolError("Access denied")  # generic on purpose: callers learn nothing about why

def _authenticate(auth_token: str, tool: str) -> dict:
    if not auth_token or not auth_token.strip():
        _deny(tool, "missing_token")
    try:
        claims = jwt.decode(auth_token, _SECRET, algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUER)
    except JWTError as exc:
        _deny(tool, "invalid_token", error=type(exc).__name__)
    if not claims.get("sub") or not claims.get("role"):
        _deny(tool, "missing_claims")
    return claims

def _is_admin(claims: dict) -> bool:
    return str(claims["role"]).lower() == "admin"

def _authorize_owner(claims: dict, owner_id: str, tool: str, *, allow_admin: bool = True) -> None:
    actor = claims["sub"]
    if actor == owner_id:
        return
    if allow_admin and _is_admin(claims):
        logger.info("ADMIN_ACCESS tool=%s actor=%s target_owner=%s", tool, actor, owner_id)  # audit trail
        return
    _deny(tool, "owner_mismatch", actor=actor, target=owner_id)

def _require(value: str, name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{name} is required")
    return value

@mcp.tool(
    title="Index a Document",
    annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False)
)

def index_document(
    owner_id:str,
    document_id:str,
    filename:str,
    chunks:list[str],
    version_id:str,
    auth_token:str
) -> str:
   claims = _authenticate(auth_token,"index_document")

   _require(owner_id, "owner_id")
   _require(document_id, "document_id")
   _require(filename, "filename")
   _require(version_id, "version_id")
   _authorize_owner(claims, owner_id, "index_document",allow_admin=False)

   if not chunks or not any(chunk.strip() for chunk in chunks):
       raise ValueError("At least one non-empty chunk is required")

   try:
       count = vector_store.index_chunks(
           owner_id=owner_id,
           document_id=document_id,
           filename=filename,
           chunks=chunks,
           version_id=version_id,
       )
   finally:
       hybrid_search.invalidate_all()

   return json.dumps({"chunk_count": count})

@mcp.tool(
    title="Search a Document",
    annotations=ToolAnnotations(
        read_only_hint=True,
        open_world_hint=False,
    ),
)
def search_document(
    owner_id: str,
    query: str,
    active_versions: dict[str, str],
    auth_token: str,
    k: int = 4,
    mode: Literal["hybrid", "dense", "bm25"] = "hybrid",
) -> str:
    try:
        claims = _authenticate(auth_token, "search_document")

        _require(query, "query")
        _require(owner_id, "owner_id")
        _authorize_owner(claims, owner_id, "search_document")

        if len(active_versions) > MAX_ACTIVE_DOCS:
           raise ValueError(f"active_versions exceeds {MAX_ACTIVE_DOCS} documents")

        k = max(1, min(k, 20))

        results = hybrid_search.search(
            owner_id=owner_id,
            query=query,
            k=k,
            mode=mode,
            active_versions=active_versions,
        )
        logger.info("SEARCH owner=%s mode=%s results=%d query_len=%d", owner_id, mode, len(results), len(query))
        return json.dumps(results)

    except Exception:
        logging.exception("search_document failed")
        raise

@mcp.tool(
    title="Delete a Document",
    annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False, destructive_hint=True)
)
def delete_document(document_id: str, auth_token: str) -> str:
    try:
        claims = _authenticate(auth_token, "delete_document")


        _require(document_id, "document_id")

        owner_id = vector_store.get_document_owner(document_id)

        if owner_id is None:
            logging.info("Delete skipped: no document found for document_id=%s", document_id)
            return json.dumps({"deleted_chunks": 0})

        _authorize_owner(claims, owner_id, "delete_document")
        logging.info(
            "Delete authorized: actor_id=%s, role=%s, owner_id=%s, document_id=%s",
            claims.get("sub"),
            claims.get("role"),
            owner_id,
            document_id,
        )
        try:
           deleted = vector_store.delete_document(document_id)
        finally:
           hybrid_search.invalidate_all()
        logging.info(
            "Delete succeeded: document_id=%s, deleted_chunks=%s",
            document_id,
            deleted,
        )
        return json.dumps({"deleted_chunks": deleted})

    except Exception:
        logging.exception("delete_document failed")
        raise


if __name__ == "__main__":
    vector_store.warm_up()
    # 127.0.0.1, not 0.0.0.0: only the backend on this machine may call this server.
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8081)
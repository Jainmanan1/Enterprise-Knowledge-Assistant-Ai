import json
import logging
from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from retrieval import vector_store
import os
from jose import jwt, JWTError

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

mcp = MCPServer(
    name="knowledge-retrieval"
)

def _authenticate(auth_token: str) -> dict:
    logging.info("Starting MCP auth check. token_present=%s", bool(auth_token))
    if not auth_token or not auth_token.strip():
        raise ValueError("Missing auth_token")
    secret = os.environ["MCP_TOKEN"]
    logging.info("MCP_TOKEN loaded? %s", bool(secret))
    if not secret:
        raise RuntimeError("MCP_TOKEN is missing from environment")

    try:
        claims = jwt.decode(
            auth_token,
            secret,
            algorithms=["HS256"],
            audience="knowledge-retrieval",
            issuer="enterprise-knowledge-assistant-backend",
        )
        logging.info("JWT decoded successfully. claims=%s", claims)
    except JWTError as exc:
        logging.exception("JWT decode failed for MCP auth")
        raise ValueError("Invalid or expired MCP authentication token") from exc

    if not claims.get("sub") or not claims.get("role"):
        logging.warning("JWT missing required claims: %s", claims)
        raise ValueError("Token is missing required identity claims")

    return claims


def _is_admin(claims: dict) -> bool:
    return claims["role"].lower() == "admin"


def _authorize_owner(claims: dict, owner_id: str) -> None:
    logging.info(
        "Checking ownership: actor_id=%s role=%s owner_id=%s",
        claims.get("sub"),
        claims.get("role"),
        owner_id,
    )    
    if not _is_admin(claims) and claims["sub"] != owner_id:
        raise PermissionError("You cannot access another user's documents")


def _require(value:str,name:str) -> str:

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
   claims = _authenticate(auth_token)

   _require(owner_id, "owner_id")
   _require(document_id, "document_id")
   _require(filename, "filename")
   _require(version_id, "version_id")
   _authorize_owner(claims, owner_id)

   if not chunks or not any(chunk.strip() for chunk in chunks):
       raise ValueError("At least one non-empty chunk is required")
    
   count = vector_store.index_chunks(
        owner_id=owner_id,
        document_id=document_id,
        filename=filename,
        chunks=chunks,
        version_id=version_id
    )
   return json.dumps({"chunk_count":count})


@mcp.tool(
    title="Search a Document",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False)
)

def search_document(
    owner_id:str,query:str,auth_token:str,k:int=4
):
    try:
        claims = _authenticate(auth_token)
        logging.info(
            "Search authorization check: actor_id=%s, role=%s, requested_owner_id=%s",
            claims.get("sub"),
            claims.get("role"),
            owner_id,
        )

        _require(query, "query")
        _require(owner_id, "owner_id")
        _authorize_owner(claims, owner_id)

        k = max(1, min(k, 20))
        result = vector_store.search(owner_id, query, k)
        logging.info("Search succeeded for owner_id=%s query=%s result_count=%s", owner_id, query, len(result))
        return json.dumps(result)

    except Exception:
        logging.exception("search_document failed")
        raise



@mcp.tool(
    title="Delete a Document",
    annotations=ToolAnnotations(read_only_hint=False, open_world_hint=False, destructive_hint=True)
)
def delete_document(document_id: str, auth_token: str) -> str:
    try:
        claims = _authenticate(auth_token)
        logging.info(
            "Delete authorization check: actor_id=%s, role=%s, document_id=%s",
            claims.get("sub"),
            claims.get("role"),
            document_id,
        )

        _require(document_id, "document_id")

        owner_id = vector_store.get_document_owner(document_id)
        logging.info("Delete owner lookup: document_id=%s, owner_id=%s", document_id, owner_id)

        if owner_id is None:
            logging.info("Delete skipped: no document found for document_id=%s", document_id)
            return json.dumps({"deleted_chunks": 0})

        _authorize_owner(claims, owner_id)
        logging.info(
            "Delete authorized: actor_id=%s, role=%s, owner_id=%s, document_id=%s",
            claims.get("sub"),
            claims.get("role"),
            owner_id,
            document_id,
        )

        deleted = vector_store.delete_document(document_id)
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

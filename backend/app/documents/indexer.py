import os
from datetime import datetime, timedelta, timezone
from jose import jwt
from app.chat.mcp_client import call_tool_sync
from dotenv import load_dotenv
load_dotenv()

def create_mcp_token(actor_id: str, actor_role: str) -> str:
    secret = os.environ["MCP_TOKEN"]

    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(actor_id),
        "role": actor_role.lower(),
        "aud": "knowledge-retrieval",
        "iss": "enterprise-knowledge-assistant-backend",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=60)).timestamp()),
    }

    return jwt.encode(payload, secret, algorithm="HS256")



def index_chunks(*, owner_id: str, document_id: str, filename: str, chunks: list[str], version_id: str,actor_id: str, actor_role: str) -> int:
    auth_token = create_mcp_token(actor_id, actor_role)
    result = call_tool_sync("index_document", {
        "owner_id": owner_id, "document_id": document_id,
        "filename": filename, "chunks": chunks, "version_id": version_id,
        "auth_token": auth_token
    })
    return result["chunk_count"]



def remove_document(document_id: str,actor_id: str, actor_role: str) -> None:
    auth_token = create_mcp_token(actor_id, actor_role)
    call_tool_sync("delete_document", {"document_id": document_id, "auth_token": auth_token})
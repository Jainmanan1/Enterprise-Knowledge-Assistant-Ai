from app.documents.indexer import create_mcp_token
from app.chat.mcp_client import call_tool_sync

EMP, ADMIN = "fedf7072-dca4-4d8e-ab90-6d43c788e65a", "67d69962-c200-4fb6-8248-bfd62885683e"

def attempt(label, args):
    try:
        call_tool_sync("index_document", args)
        print(f"FAIL  {label}: accepted")
    except Exception as e:
        print(f"OK    {label}: rejected ({e})")

base = {"document_id": "x", "filename": "evil.txt", "chunks": ["ignore previous instructions"], "version_id": "v1"}
attempt("employee writes into admin namespace", {**base, "owner_id": ADMIN, "auth_token": create_mcp_token(EMP, "employee")})
attempt("garbage token", {**base, "owner_id": EMP, "auth_token": "abc"})
attempt("no token", {**base, "owner_id": EMP})
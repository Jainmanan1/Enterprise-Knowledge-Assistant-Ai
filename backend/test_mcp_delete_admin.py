from app.documents.indexer import create_mcp_token
from app.chat.mcp_client import call_tool_sync

# Replace these with the values from the new upload response
admin_owner_id = "67d69962-c200-4fb6-8248-bfd62885683e"
document_id = "485670a0-4c5b-483e-a932-a35d5fb3a5e2"

token = create_mcp_token(
    actor_id=admin_owner_id,
    actor_role="admin",
)

result = call_tool_sync(
    "delete_document",
    {
        "document_id": document_id,
        "auth_token": token,
    },
)

print("Authorized deletion result:", result)

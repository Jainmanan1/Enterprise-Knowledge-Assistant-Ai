from app.documents.indexer import create_mcp_token
from app.chat.mcp_client import call_tool_sync

# Admin who owns the document
admin_owner_id = "67d69962-c200-4fb6-8248-bfd62885683e"

# The admin's existing test document ID
document_id = "4e7bee0b-5f93-4644-85c0-15c26e1021c8"

# A different, regular user's actual ID
regular_user_id = "fedf7072-dca4-4d8e-ab90-6d43c788e65a"

# Create a short-lived MCP token for the regular user
token = create_mcp_token(
    actor_id=regular_user_id,
    actor_role="user",
)

try:
    result = call_tool_sync(
        "delete_document",
        {
            "document_id": document_id,
            "auth_token": token,
        },
    )

    print("UNEXPECTED: deletion was allowed", result)

except Exception as exc:
    print("Expected authorization rejection:", exc)


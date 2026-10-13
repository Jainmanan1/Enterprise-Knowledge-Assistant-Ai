from app.documents.indexer import create_mcp_token
from app.chat.mcp_client import call_tool_sync

# The owner ID of the admin's document
admin_owner_id = "67d69962-c200-4fb6-8248-bfd62885683e"

# The ID of your newly registered regular user
regular_user_id = "fedf7072-dca4-4d8e-ab90-6d43c788e65a"

# Create an MCP token representing the regular user
token = create_mcp_token(
    actor_id=regular_user_id,
    actor_role="user",
)

try:
    result = call_tool_sync(
        "search_document",
        {
            "owner_id": admin_owner_id,
            "query": "hello my name is manan",
            "auth_token": token,
            "k": 4,
        },
    )
    print("UNEXPECTED: access succeeded", result)

except Exception as exc:
    print("Expected authorization rejection:", exc)
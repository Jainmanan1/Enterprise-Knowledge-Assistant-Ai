"""Verify that a deleted document no longer appears in MCP search."""

import os

def main() -> None:
    from _bootstrap import prepare_backend

    prepare_backend()

    from app.documents.indexer import create_mcp_token
    from app.chat.mcp_client import call_tool_sync

    owner_id = os.environ.get("TEST_OWNER_ID")
    document_id = os.environ.get("TEST_DELETED_DOCUMENT_ID")

    if not owner_id or not document_id:
        raise SystemExit(
            "Set TEST_OWNER_ID and TEST_DELETED_DOCUMENT_ID "
            "to the test owner and deleted document IDs."
        )

    token = create_mcp_token(
        actor_id=owner_id,
        actor_role="admin",
    )

    results = call_tool_sync(
        "search_document",
        {
            "owner_id": owner_id,
            "query": "This is a disposable document for testing authorized deletion",
            "auth_token": token,
            "k": 20,
        },
    )

    matching_chunks = [
        result
        for result in results
        if result.get("document_id") == document_id
    ]

    if matching_chunks:
        print("FAIL: Deleted document still has searchable chunks")
        print(f"Matching chunks found: {len(matching_chunks)}")
        raise SystemExit(1)

    print("PASS: No matching chunks found for the deleted document")
    print(f"Other search results: {len(results)}")


if __name__ == "__main__":
    main()

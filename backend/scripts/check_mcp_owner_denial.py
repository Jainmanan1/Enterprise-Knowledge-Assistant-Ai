

def main():
    from _bootstrap import prepare_backend

    prepare_backend()

    from app.db.session import SessionLocal
    from app.documents.indexer import search_chunks

    OWNER_ID = "67d69962-c200-4fb6-8248-bfd62885683e"  # Admin
    EMPLOYEE_ID = "bd63ca31-2d3e-4182-8893-cc41e8a69518"  # Employee
    db = SessionLocal()

    try:
        print("Attempting cross-owner search as an employee...")

        try:
            search_chunks(
                db=db,
                owner_id=OWNER_ID,
                query="hello my name is manan jain",
                actor_id=EMPLOYEE_ID,
                actor_role="employee",
                k=4,
            )

        except RuntimeError as exc:
            message = str(exc)
            print(f"Request rejected: {type(exc).__name__}: {message}")

            # MCP deliberately hides the underlying server exception.
            if (
                "MCP tool 'search_document' failed" in message
                and "Error executing tool search_document" in message
            ):
                print(
                    "PASS: MCP rejected the request. "
                    "Confirm AUTH_DENIED reason=owner_mismatch "
                    "in the MCP server logs."
                )
            else:
                raise AssertionError(
                    "Unexpected RuntimeError; denial is not confirmed."
                ) from exc

        else:
            raise AssertionError(
                "FAIL: Employee was allowed to search another owner's documents."
            )

    finally:
        db.close()


if __name__ == "__main__":
    main()


def main() -> None:
    from _bootstrap import prepare_backend

    prepare_backend()

    from app.db.session import SessionLocal
    from app.documents.recovery import recover_pending_deletions

    document_ids = [
        "a2feaed9-d62f-42c5-915c-83309690f791",
        "cc579493-9cea-4b9a-97ba-d06a2620cc7d",
    ]

    db = SessionLocal()
    try:
        result = recover_pending_deletions(
            db,
            document_ids=document_ids,
        )
        print("Recovery result:", result)
    finally:
        db.close()


if __name__ == "__main__":
    main()

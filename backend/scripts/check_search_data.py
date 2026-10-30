
"""Inspect active SQL documents and their version mappings."""

def main() -> None:
    from _bootstrap import prepare_backend

    prepare_backend()

    from app.db.session import SessionLocal
    from app.db.models import Document
    from app.documents.indexer import get_active_versions

    db = SessionLocal()

    try:
        documents = (
            db.query(Document)
            .filter(Document.deletion_status == "active")
            .all()
        )

        print(f"Active SQL documents: {len(documents)}")

        owners = {document.owner_id for document in documents}

        # Print a summary instead of exposing document and owner IDs.
        print(f"Distinct owners with active documents: {len(owners)}")

        for owner_id in owners:
            versions = get_active_versions(db, owner_id)
            print(f"\nActive version mappings for one owner:")
            print(f"Mapped document count: {len(versions)}")

    finally:
        db.close()


if __name__ == "__main__":
    main()

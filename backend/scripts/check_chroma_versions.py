
"""Check active SQL document versions against Chroma metadata."""

def main() -> None:
    from _bootstrap import prepare_backend

    prepare_backend()

    from app.db.session import SessionLocal
    from app.db.models import Document
    from app.documents.indexer import get_active_versions
    # ``prepare_backend`` adds the backend root to ``sys.path`` at runtime.
    from retrieval import vector_store  # pyright: ignore[reportMissingImports]

    db = SessionLocal()

    try:
        documents = (
            db.query(Document)
            .filter(
                Document.deletion_status == "active",
                Document.active_version_id.isnot(None),
            )
            .all()
        )

        print(f"Checking {len(documents)} active SQL documents\n")

        for document in documents:
            versions = get_active_versions(db, document.owner_id)
            active_version = versions.get(document.id)

            if active_version is None:
                print(f"SKIP: {document.id} has no active version mapping")
                continue

            # Initialize the lazy Chroma store through its accessor.
            store = vector_store._get_store()
            records = store.get(
                where={
                    "$and": [
                        {"owner_id": str(document.owner_id)},
                        {"document_id": str(document.id)},
                    ]
                },
                include=["metadatas"],
            )

            metadatas = records.get("metadatas") or []
            matching = [
                metadata
                for metadata in metadatas
                if metadata
                and metadata.get("indexing_version") == active_version
            ]

            print(f"Document: {document.id}")
            print(f"  SQL active version: {active_version}")
            print(f"  Chroma chunks for document: {len(metadatas)}")
            print(f"  Chroma chunks for active version: {len(matching)}")
            print(
                f"  Status: "
                f"{'PASS' if matching else 'NO MATCHING ACTIVE CHUNKS'}"
            )
            print()
    finally:
        db.close()


if __name__ == "__main__":
    main()

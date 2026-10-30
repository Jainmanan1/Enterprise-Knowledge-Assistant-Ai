


def main() -> None:
    from _bootstrap import prepare_backend

    prepare_backend()

    from app.db.models import Document
    from app.db.session import SessionLocal
    from app.documents.indexer import get_active_versions, search_chunks

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
        if not documents:
            print("No active, versioned documents found in SQL.")
            return

        owner_id = documents[0].owner_id
        active_versions = get_active_versions(db=db, owner_id=owner_id)
        print("Owner:", owner_id)
        print("Active versions:", active_versions)
        results = search_chunks(
            db=db,
            owner_id=owner_id,
            query="what is the name inside the document?",
            actor_id=owner_id,
            actor_role="employee",
            k=4,
        )
        print("Number of results:", len(results))
        for item in results:
            print("Document:", item["document_id"])
            print("Returned version:", item["indexing_version"])
            print("Text:", item["text"][:150])
            assert active_versions.get(item["document_id"]) == item["indexing_version"], (
                f"Stale or unexpected version returned: {item}"
            )
        print("PASS: Every returned chunk matches its SQL active version.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

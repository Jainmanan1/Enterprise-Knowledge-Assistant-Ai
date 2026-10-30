
from _bootstrap import prepare_project_imports
from importlib import import_module

DOCUMENT_IDS = [
    "a2feaed9-d62f-42c5-915c-83309690f791",
    "cc579493-9cea-4b9a-97ba-d06a2620cc7d",
]


def main() -> None:
    # Prepare imports and load application services only when the script runs.
    prepare_project_imports()

    from retrieval import vector_store
    # Resolve this module after the project import path has been prepared.
    init_db = import_module("app.db.init_db").init_db
    SessionLocal = import_module("app.db.session").SessionLocal
    Document = import_module("app.db.models").Document

    # Create tables if they don't exist yet.
    init_db()

    with SessionLocal() as db:
        for document_id in DOCUMENT_IDS:
            doc = (
                db.query(Document)
                .filter(Document.id == document_id)
                .first()
            )

            print(f"\nDOCUMENT: {document_id}")

            if doc is None:
                print("SQL: not found")
            else:
                print(f"SQL status: {doc.deletion_status}")

            # Access Chroma through the lazy store getter.
            records = vector_store._get_store().get(
                where={"document_id": document_id},
                include=["metadatas"],
            )
            ids = records.get("ids", [])

            if ids:
                print(f"Chroma: {len(ids)} chunks still exist")
                print("Chunk IDs:", ids)
            else:
                print("Chroma: no chunks found")


if __name__ == "__main__":
    main()

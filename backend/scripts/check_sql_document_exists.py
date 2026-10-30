
def main() -> None:
    from _bootstrap import prepare_backend

    prepare_backend()

    from app.db.session import SessionLocal
    from app.db.models import Document

    document_id = "fedf7072-dca4-4d8e-ab90-6d43c788e65a"

    db = SessionLocal()
    try:
        doc = (
            db.query(Document)
            .filter(Document.id == document_id)
            .first()
        )

        if doc:
            print("SQL RECORD STILL EXISTS")
            print("Document ID:", doc.id)
            print("Filename:", doc.filename)
            print("Owner ID:", doc.owner_id)
        else:
            print("SQL RECORD DOES NOT EXIST")
    finally:
        db.close()


if __name__ == "__main__":
    main()

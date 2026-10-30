
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.db.models import User, Document, UserRole
from app.documents import recovery


def test_recovery_ignores_active_documents(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
    )
    db = TestingSessionLocal()

    owner = User(
        id="active-test-owner",
        email="active-test@example.com",
        hashed_password="test-hash",
        role=UserRole.EMPLOYEE,
    )

    doc = Document(
        id="active-test-document",
        filename="active-test.txt",
        owner_id=owner.id,
        deletion_status="active",
        active_version_id="active-test-version",
    )

    try:
        db.add_all([owner, doc])
        db.commit()

        mock_remove = Mock(return_value=3)
        monkeypatch.setattr(recovery, "remove_document", mock_remove)

        result = recovery.recover_pending_deletions(
            db,
            document_ids=[doc.id],
        )

        assert result == {
            "found": 0,
            "recovered": 0,
            "failed": 0,
        }

        mock_remove.assert_not_called()

        remaining_doc = (
            db.query(Document)
            .filter(Document.id == doc.id)
            .one_or_none()
        )

        assert remaining_doc is not None
        assert remaining_doc.deletion_status == "active"

        print("PASS: Active document was not selected.")
        print("PASS: Vector deletion was never called.")
        print("PASS: Active SQL document remains unchanged.")

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.db.models import User, Document, UserRole
from app.documents import recovery


def test_recovery_with_empty_document_ids_processes_nothing(monkeypatch):
    """An empty ID list should not process any pending documents."""

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
        id="empty-ids-owner",
        email="empty-ids-test@example.com",
        hashed_password="test-hash",
        role=UserRole.EMPLOYEE,
    )

    doc = Document(
        id="empty-ids-document",
        filename="pending-document.txt",
        owner_id=owner.id,
        deletion_status="deletion_pending",
        active_version_id="empty-ids-version",
    )

    try:
        db.add_all([owner, doc])
        db.commit()

        # If recovery attempts vector deletion, the mock records it.
        mock_remove = Mock(return_value=3)
        monkeypatch.setattr(recovery, "remove_document", mock_remove)

        result = recovery.recover_pending_deletions(
            db,
            document_ids=[],
        )

        assert result == {
            "found": 0,
            "recovered": 0,
            "failed": 0,
        }

        mock_remove.assert_not_called()

        # The pending document must remain untouched.
        remaining_doc = (
            db.query(Document)
            .filter(Document.id == doc.id)
            .one_or_none()
        )

        assert remaining_doc is not None
        assert remaining_doc.deletion_status == "deletion_pending"

        print("PASS: Empty ID list selected zero documents.")
        print("PASS: Vector deletion was never called.")
        print("PASS: Pending SQL document remains untouched.")

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

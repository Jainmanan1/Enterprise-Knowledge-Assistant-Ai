
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.db.models import User, Document, UserRole
from app.documents import recovery


def test_repeated_recovery_does_not_process_document_twice(monkeypatch):
    """A successfully recovered document should not be processed again."""

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
        id="recovery-test-owner",
        email="recovery-test@example.com",
        hashed_password="test-hash",
        role=UserRole.EMPLOYEE,
    )

    doc = Document(
        id="recovery-test-document",
        filename="recovery-test.txt",
        owner_id=owner.id,
        deletion_status="deletion_pending",
        active_version_id="recovery-test-version",
    )

    try:
        db.add_all([owner, doc])
        db.commit()

        # Simulate successful vector-store deletion.
        mock_remove = Mock(return_value=3)
        monkeypatch.setattr(recovery, "remove_document", mock_remove)

        # First recovery should delete the pending document.
        first_result = recovery.recover_pending_deletions(
            db,
            document_ids=[doc.id],
        )

        assert first_result == {
            "found": 1,
            "recovered": 1,
            "failed": 0,
        }

        mock_remove.assert_called_once_with(
            document_id=doc.id,
            actor_id="system-recovery",
            actor_role="admin",
        )

        remaining_doc = (
            db.query(Document)
            .filter(Document.id == doc.id)
            .one_or_none()
        )
        assert remaining_doc is None

        # Second recovery should find nothing to process.
        second_result = recovery.recover_pending_deletions(
            db,
            document_ids=[doc.id],
        )

        assert second_result == {
            "found": 0,
            "recovered": 0,
            "failed": 0,
        }

        # No second vector-store deletion attempt should occur.
        mock_remove.assert_called_once()

        print("PASS: First recovery deleted the pending SQL record.")
        print("PASS: Second recovery found no pending document.")
        print("PASS: Vector deletion was called only once.")

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

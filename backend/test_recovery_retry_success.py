
from unittest.mock import Mock, call

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.db.models import User, Document, UserRole
from app.documents import recovery


def test_recovery_retries_after_transient_vector_failure(monkeypatch):
    """A pending document can be recovered after a temporary failure."""

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

        # First call fails; second call succeeds.
        mock_remove = Mock(
            side_effect=[
                RuntimeError("Temporary vector-store failure"),
                3,
            ]
        )
        monkeypatch.setattr(recovery, "remove_document", mock_remove)

        # First recovery: vector deletion fails.
        first_result = recovery.recover_pending_deletions(
            db,
            document_ids=[doc.id],
        )

        assert first_result == {
            "found": 1,
            "recovered": 0,
            "failed": 1,
        }

        remaining_doc = (
            db.query(Document)
            .filter(Document.id == doc.id)
            .one_or_none()
        )

        assert remaining_doc is not None
        assert remaining_doc.deletion_status == "deletion_pending"

        # Second recovery: vector deletion succeeds.
        second_result = recovery.recover_pending_deletions(
            db,
            document_ids=[doc.id],
        )

        assert second_result == {
            "found": 1,
            "recovered": 1,
            "failed": 0,
        }

        # The document should now be deleted from SQL.
        remaining_doc = (
            db.query(Document)
            .filter(Document.id == doc.id)
            .one_or_none()
        )
        assert remaining_doc is None

        expected_call = call(
            document_id=doc.id,
            actor_id="system-recovery",
            actor_role="admin",
        )

        assert mock_remove.call_count == 2
        assert mock_remove.call_args_list == [
            expected_call,
            expected_call,
        ]

        print("PASS: First recovery failed and preserved the document.")
        print("PASS: Second recovery successfully deleted the document.")
        print("PASS: Vector deletion was attempted exactly twice.")

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

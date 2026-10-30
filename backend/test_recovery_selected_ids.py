
from unittest.mock import Mock, call

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.db.models import User, Document, UserRole
from app.documents import recovery


def test_recovery_processes_only_selected_document_ids(monkeypatch):
    """Recovery should process only the requested pending documents."""

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
        id="selected-recovery-owner",
        email="selected-recovery@example.com",
        hashed_password="test-hash",
        role=UserRole.EMPLOYEE,
    )

    first_doc = Document(
        id="selected-document-1",
        filename="selected-1.txt",
        owner_id=owner.id,
        deletion_status="deletion_pending",
        active_version_id="selected-version-1",
    )

    second_doc = Document(
        id="selected-document-2",
        filename="selected-2.txt",
        owner_id=owner.id,
        deletion_status="deletion_pending",
        active_version_id="selected-version-2",
    )

    try:
        db.add_all([owner, first_doc, second_doc])
        db.commit()

        # Simulate successful vector deletion.
        mock_remove = Mock(return_value=3)
        monkeypatch.setattr(recovery, "remove_document", mock_remove)

        # Request recovery for only the first document.
        result = recovery.recover_pending_deletions(
            db,
            document_ids=[first_doc.id],
        )

        assert result == {
            "found": 1,
            "recovered": 1,
            "failed": 0,
        }

        # Only the selected document should be processed.
        mock_remove.assert_called_once_with(
            document_id=first_doc.id,
            actor_id="system-recovery",
            actor_role="admin",
        )

        # The selected document should be deleted from SQL.
        remaining_first = (
            db.query(Document)
            .filter(Document.id == first_doc.id)
            .one_or_none()
        )
        assert remaining_first is None

        # The unselected pending document should remain untouched.
        remaining_second = (
            db.query(Document)
            .filter(Document.id == second_doc.id)
            .one_or_none()
        )
        assert remaining_second is not None
        assert remaining_second.deletion_status == "deletion_pending"

        print("PASS: Only the selected document was recovered.")
        print("PASS: Selected document was deleted from SQL.")
        print("PASS: Unselected pending document remains pending.")
        print("PASS: Vector deletion was called exactly once.")

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

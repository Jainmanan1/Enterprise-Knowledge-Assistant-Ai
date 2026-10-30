
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.db.models import User, Document, UserRole
from app.documents import recovery


def test_recovery_vector_deletion_failure_keeps_document_pending(
    monkeypatch,
):
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
        id="recovery-failure-owner",
        email="recovery-failure@example.com",
        hashed_password="test-hash",
        role=UserRole.EMPLOYEE,
    )

    doc = Document(
        id="recovery-failure-document",
        filename="recovery-failure.txt",
        owner_id=owner.id,
        deletion_status="deletion_pending",
        active_version_id="recovery-failure-version",
    )

    try:
        db.add_all([owner, doc])
        db.commit()

        mock_remove = Mock(
            side_effect=RuntimeError("Simulated vector deletion failure")
        )
        monkeypatch.setattr(recovery, "remove_document", mock_remove)

        result = recovery.recover_pending_deletions(
            db,
            document_ids=[doc.id],
        )

        assert result == {
            "found": 1,
            "recovered": 0,
            "failed": 1,
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

        assert remaining_doc is not None
        assert remaining_doc.deletion_status == "deletion_pending"

        print("PASS: Recovery found the pending document.")
        print("PASS: Vector deletion failure was counted.")
        print("PASS: SQL document remains pending for retry.")

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

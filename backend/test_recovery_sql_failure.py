
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.db.models import User, Document, UserRole
from app.documents import recovery


def test_recovery_sql_cleanup_failure_keeps_document_pending(monkeypatch):
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
        id="recovery-sql-owner",
        email="recovery-sql-failure@example.com",
        hashed_password="test-hash",
        role=UserRole.EMPLOYEE,
    )

    doc = Document(
        id="recovery-sql-document",
        filename="recovery-sql-failure.txt",
        owner_id=owner.id,
        deletion_status="deletion_pending",
        active_version_id="recovery-sql-version",
    )

    try:
        db.add_all([owner, doc])
        db.commit()

        # Vector deletion succeeds.
        mock_remove = Mock(return_value=3)
        monkeypatch.setattr(recovery, "remove_document", mock_remove)

        # Fail the SQL commit used to remove the Document row.
        real_commit = db.commit
        commit_calls = 0

        def fail_cleanup_commit():
            nonlocal commit_calls
            commit_calls += 1
            raise SQLAlchemyError("Simulated SQL cleanup failure")

        monkeypatch.setattr(db, "commit", fail_cleanup_commit)

        result = recovery.recover_pending_deletions(
            db,
            document_ids=[doc.id],
        )

        assert result == {
            "found": 1,
            "recovered": 0,
            "failed": 1,
        }

        assert commit_calls == 1

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

        print("PASS: Vector deletion succeeded.")
        print("PASS: SQL cleanup failure was counted.")
        print("PASS: SQL document remains pending for retry.")

    finally:
        db.commit = real_commit if "real_commit" in locals() else db.commit
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

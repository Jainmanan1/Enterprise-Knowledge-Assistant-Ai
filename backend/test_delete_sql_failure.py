
import pytest

from unittest.mock import Mock
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

from app.db.session import Base
from app.db.models import User, Document, UserRole
from app.documents import routes as document_routes


def test_chroma_deletion_succeeds_but_sql_delete_commit_fails(monkeypatch):
    """SQL metadata should remain deletion_pending if its final commit fails."""

    # Use an isolated in-memory database; do not modify app.db.
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
        id="test-owner-id",
        email="deletion-test@example.com",
        hashed_password="test-hash",
        role=UserRole.EMPLOYEE,
    )
    doc = Document(
        id="test-document-id",
        filename="deletion-test.txt",
        owner_id=owner.id,
        deletion_status="active",
        active_version_id="test-version-id",
    )

    try:
        db.add_all([owner, doc])
        db.commit()

        # Simulate a successful ChromaDB/MCP deletion.
        # No real vector data will be deleted by this test.
        mock_remove = Mock(return_value=3)
        monkeypatch.setattr(
            document_routes,
            "remove_document",
            mock_remove,
        )

        # Allow the first commit (deletion_pending) to succeed.
        # Fail only the second commit (SQL row deletion).
        real_commit = db.commit
        commit_calls = 0

        def fail_second_commit():
            nonlocal commit_calls
            commit_calls += 1

            if commit_calls == 2:
                raise SQLAlchemyError(
                    "Simulated final SQL commit failure"
                )

            return real_commit()

        monkeypatch.setattr(db, "commit", fail_second_commit)

        with pytest.raises(HTTPException) as exc_info:
            document_routes.delete_document(
                document_id=doc.id,
                current_user=owner,
                db=db,
            )

        # The endpoint should report the SQL deletion failure.
        assert exc_info.value.status_code == 500
        assert "SQL deletion failed" in exc_info.value.detail

        # Both endpoint commits were attempted.
        assert commit_calls == 2

        # The vector deletion function was called successfully.
        mock_remove.assert_called_once_with(
            document_id=doc.id,
            actor_id=owner.id,
            actor_role=owner.role.value,
        )

        # Rollback should leave the previously committed pending row.
        remaining_doc = (
            db.query(Document)
            .filter(Document.id == doc.id)
            .one_or_none()
        )

        assert remaining_doc is not None
        assert remaining_doc.deletion_status == "deletion_pending"

        print("PASS: ChromaDB deletion reported success.")
        print("PASS: Final SQL commit failed as expected.")
        print("PASS: Document remains in SQL.")
        print("PASS: Document status is deletion_pending.")

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

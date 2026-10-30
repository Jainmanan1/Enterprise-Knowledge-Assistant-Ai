
import pytest
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

from app.db.session import Base
from app.db.models import User, Document, UserRole
from app.documents import routes as document_routes


def test_mcp_deletion_failure_keeps_document_pending(monkeypatch):
    """A vector-store failure must leave the document pending for recovery."""

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
        email="mcp-failure-test@example.com",
        hashed_password="test-hash",
        role=UserRole.EMPLOYEE,
    )

    doc = Document(
        id="test-document-id",
        filename="mcp-failure-test.txt",
        owner_id=owner.id,
        deletion_status="active",
        active_version_id="test-version-id",
    )

    try:
        db.add_all([owner, doc])
        db.commit()

        # Simulate MCP/ChromaDB deletion failure.
        mock_remove = Mock(
            side_effect=RuntimeError("Simulated MCP deletion failure")
        )

        monkeypatch.setattr(
            document_routes,
            "remove_document",
            mock_remove,
        )

        with pytest.raises(HTTPException) as exc_info:
            document_routes.delete_document(
                document_id=doc.id,
                current_user=owner,
                db=db,
            )

        # The endpoint should report vector-store failure.
        assert exc_info.value.status_code == 502
        assert "Vector-store deletion failed" in exc_info.value.detail

        # Confirm MCP deletion was attempted exactly once.
        mock_remove.assert_called_once_with(
            document_id=doc.id,
            actor_id=owner.id,
            actor_role=owner.role.value,
        )

        # Confirm the SQL row still exists and is pending recovery.
        remaining_doc = (
            db.query(Document)
            .filter(Document.id == doc.id)
            .one_or_none()
        )

        assert remaining_doc is not None
        assert remaining_doc.deletion_status == "deletion_pending"

        print("PASS: MCP deletion failure was simulated.")
        print("PASS: Endpoint returned HTTP 502.")
        print("PASS: SQL document still exists.")
        print("PASS: Document remains deletion_pending.")

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

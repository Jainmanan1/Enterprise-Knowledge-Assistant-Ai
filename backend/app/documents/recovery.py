import logging

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Document
from app.documents.indexer import remove_document

logger = logging.getLogger(__name__)


def  recover_pending_deletions(
        db: Session,
        document_ids:list[str] |None = None
) -> dict[str,int]:

    """
    Retry deletion for documents marked deletion_pending.

    Pass document_ids to recover only selected documents.
    If omitted, process all pending documents.
    """
    statement = select(Document).where(Document.deletion_status == "deletion_pending")

    if document_ids is not None:
        statement = statement.where(Document.id.in_(document_ids))
    pending_docs = db.scalars(statement).all()

    summary = {
        "found" : len(pending_docs),
        "recovered" : 0,
        "failed" : 0
    }

    for doc in pending_docs:
        document_id = str(doc.id)
        try:
            remove_document(
                document_id = document_id,
                actor_id = "system-recovery",
                actor_role = "admin"

            )
        except Exception:
            db.rollback()
            summary["failed"] += 1
            logger.exception(
                "Vector deletion failed during recovery: %s",
                document_id,
            )
            continue

        try:
            db.delete(doc)
            db.commit()
            summary["recovered"] += 1
            logger.info(
                "Recovered pending deletion: %s",
                document_id,
            )
        except SQLAlchemyError:
            db.rollback()

            summary["failed"] += 1
            logger.exception(
                "SQL cleanup failed during recovery: %s",
                document_id,
            )

    return summary
import os
from fastapi import APIRouter, Depends, File, status, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.db.models import User,Document,UserRole
from app.documents.indexer import index_chunks, remove_document
from app.documents.ingest import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, chunk_text, extract_text
from app.documents.model import DocumentOut, UploadResult
from sqlalchemy.exc import SQLAlchemyError
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload",response_model=UploadResult,status_code=status.HTTP_201_CREATED)

def upload_document(
    file:UploadFile = File(...),
    current_user:User = Depends(get_current_user),
    db:Session = Depends(get_db)

):
    filename = os.path.basename(file.filename or "")
    ext = os.path.splitext(filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400,detail=f"Unsupported file type. Allowed: {sorted(ALLOWED_EXTENSIONS)}")

    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    chunks = chunk_text(extract_text(filename,content))
    if not chunks:
        raise HTTPException(status_code=400, detail="No extractable text found in file")

    doc = Document(owner_id=current_user.id,filename=filename)
    db.add(doc)
    db.flush()  # Ensure doc.id is populated

    try:
        version_id = str(uuid.uuid4())
        count = index_chunks(
            owner_id = current_user.id,
            document_id = str(doc.id),
            filename = filename,
            chunks = chunks,
            version_id = version_id,
            actor_id = str(current_user.id),
            actor_role = current_user.role.value
        )
    except Exception:
        db.rollback()
        raise HTTPException(status_code=502, detail="Indexing failed")
    doc.active_version_id = version_id
    db.commit()
    db.refresh(doc)
    return UploadResult(
    id=doc.id,
    filename=doc.filename,
    owner_id=doc.owner_id,
    uploaded_at=doc.uploaded_at,
    chunk_count=count,
)

@router.get("",response_model=list[DocumentOut])

def list_documents(
    current_user:User = Depends(get_current_user),
    db:Session = Depends(get_db)

):
    query = db.query(Document)
    if current_user.role != UserRole.ADMIN:
        query = query.filter(Document.owner_id == current_user.id)
    return query.order_by(Document.uploaded_at.desc()).all()


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(
    document_id:str,
    current_user:User  = Depends(get_current_user),
    db:Session = Depends(get_db)
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc is None or (doc.owner_id != current_user.id and current_user.role != UserRole.ADMIN):
        raise HTTPException(status_code=404, detail="Document not found")
    # Check ownership or admin privileges.
    is_admin = current_user.role == UserRole.ADMIN
    is_owner = str(doc.owner_id) == str(current_user.id)
    if not (is_admin or is_owner):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can not delete another user's document")
    doc.deletion_status = "deletion_pending"
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception(
            "Failed to mark document for deletion: %s",
            document_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not initiate document deletion",
        ) from exc
        #Delete Chroma chunks through MCP first.
    try:
        deleted_chunks = remove_document(document_id=str(doc.id), actor_id=str(current_user.id), actor_role=current_user.role.value)
    except Exception as e:
        db.rollback()
        logger.exception(
        "MCP deletion failed for document_id=%s",
        document_id,
    )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Vector-store deletion failed. "
                "Document is marked for recovery.",
        ) from e
    #Delete SQL metadata only after MCP reports success.
    try:
        db.delete(doc)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        # Chroma may already have been deleted.
        # This needs recovery/reconciliation.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Vector chunks were deleted, but SQL deletion failed. "
                "The document requires reconciliation."
            ),
        ) from exc

    return {
        "message": "Document deleted successfully",
        "document_id": document_id,
        "deleted_chunks": deleted_chunks,
    }
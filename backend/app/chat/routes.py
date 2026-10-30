from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.db.models import User
from app.documents.indexer import search_chunks

router = APIRouter(prefix="/chat",tags=["chat"])

class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=4, ge=1 ,le=20)


@router.post("/search")

def search_chat(
    request: SearchRequest,
    current_user:User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = request.query.strip()
    if not query:
        raise HTTPException(
            status_code=400,
            detail="Query cannot be empty",
        )

    try:
        results = search_chunks(
            db=db,
            owner_id=current_user.id,
            query=query,
            actor_id=current_user.id,
            actor_role=current_user.role.value,
            k=request.k

        )
        return {
            "query": query,
            "result_count": len(results),
            "results": results,

        }
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Document search failed",
        )
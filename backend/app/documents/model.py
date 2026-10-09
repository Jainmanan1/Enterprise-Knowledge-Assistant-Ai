from datetime import datetime
from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:str
    filename:str
    owner_id:str
    uploaded_at:datetime


class UploadResult(BaseModel):
    chunk_count:int    


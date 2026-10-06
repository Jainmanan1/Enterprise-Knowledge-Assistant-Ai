from pydantic import BaseModel, ConfigDict, EmailStr
from app.db.models import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    email: EmailStr
    role: UserRole
    model_config = ConfigDict(from_attributes=True)
    


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
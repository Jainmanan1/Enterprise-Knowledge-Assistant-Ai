from pydantic import BaseModel, EmailStr
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

    class Config:
        from_attributes = True


class token(BaseModel):
    access_token: str
    token_type: str = "bearer"
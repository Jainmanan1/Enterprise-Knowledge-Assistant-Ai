import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship

from app.db.session import Base

class UserRole(str,enum.Enum):
    ADMIN = "admin"
    EMPLOYEE = "employee"

class User(Base):
    __tablename__ = "users" 

    id = Column(String, primary_key=True, default = lambda: str(uuid.uuid4()))   
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.EMPLOYEE)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    documents = relationship("Document", back_populates="owner")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda:str(uuid.uuid4()))   
    filename = Column(String, nullable=False) 
    owner_id = Column(String,ForeignKey("users.id"),nullable=False,index=True)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    owner = relationship("User",back_populates = "documents")

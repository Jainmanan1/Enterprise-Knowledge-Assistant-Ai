# backend/app/main.py
from fastapi import FastAPI
from app.auth.routes import router as auth_router
from app.db.init_db import init_db
from app.documents.routes import router as documents_router

app = FastAPI(title="Enterprise Knowledge Assistant")

init_db()  # creates tables if they don't exist yet
app.include_router(auth_router)
app.include_router(documents_router)

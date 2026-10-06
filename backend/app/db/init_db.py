from app.db.session import engine, Base
from app.db import models  # import so Base knows about the tables

def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
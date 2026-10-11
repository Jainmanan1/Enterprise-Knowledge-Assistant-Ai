from app.db.session import SessionLocal
from app.db.models import User, UserRole

db = SessionLocal()
user = db.query(User).filter(User.email == "your@email.com").first()
if user is None:
	raise ValueError("User not found")
user.role = UserRole.ADMIN
db.commit()
print(f"{user.email} is now {user.role.value}")

"""Summarize users in the database without exposing user IDs."""

def main() -> None:
    from _bootstrap import prepare_backend

    prepare_backend()

    from collections import Counter
    from app.db.session import SessionLocal
    from app.db.models import User

    db = SessionLocal()
    try:
        users = db.query(User).all()

        role_counts = Counter(user.role.value for user in users)

        print(f"Users found: {len(users)}")
        print("Users by role:")

        for role, count in sorted(role_counts.items()):
            print(f"  {role}: {count}")

    finally:
        db.close()


if __name__ == "__main__":
    main()

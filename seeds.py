from database.session import (
    create_db_and_tables,
    engine
)

from sqlmodel import Session

from models.user import User

from auth import hash_password


def seed():

    create_db_and_tables()

    with Session(engine) as session:

        admin = session.query(User).filter(
            User.username == "admin"
        ).first()

        if admin:

            print("Admin already exists")
            return

        admin = User(
            username="admin",
            email="admin@sendit.com",
            full_name="System Administrator",
            hashed_password=hash_password("admin123"),
            role="admin"
        )

        manager = User(
            username="manager",
            email="manager@sendit.com",
            full_name="System Manager",
            hashed_password=hash_password("manager123"),
            role="manager"
        )

        staff = User(
            username="staff",
            email="staff@sendit.com",
            full_name="Staff User",
            hashed_password=hash_password("staff123"),
            role="staff"
        )

        session.add(admin)
        session.add(manager)
        session.add(staff)

        session.commit()

        print("Database seeded successfully")


if __name__ == "__main__":
    seed()
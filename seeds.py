from sqlmodel import Session, select

# Import BOTH models so SQLModel registers relationships
from models.user import User
from models.document import Document

from database.session import (
    engine,
    create_db_and_tables
)

from models.user import User

from auth import hash_password


def create_users():

    # Make sure tables exist
    create_db_and_tables()


    with Session(engine) as session:

        # Check if admin already exists
        existing_admin = session.exec(

            select(User).where(

                User.username
                == "admin"

            )

        ).first()


        if not existing_admin:

            admin = User(

                username="admin",

                email="admin@sendit.com",

                hashed_password=hash_password(
                    "Admin123!"
                ),

                full_name="System Administrator",

                role="admin"

            )

            session.add(
                admin
            )


        # Check manager
        existing_manager = session.exec(

            select(User).where(

                User.username
                == "manager"

            )

        ).first()


        if not existing_manager:

            manager = User(

                username="manager",

                email="manager@sendit.com",

                hashed_password=hash_password(
                    "Manager123!"
                ),

                full_name="SendIt Manager",

                role="manager"

            )

            session.add(
                manager
            )


        # Check staff
        existing_staff = session.exec(

            select(User).where(

                User.username
                == "staff"

            )

        ).first()


        if not existing_staff:

            staff = User(

                username="staff",

                email="staff@sendit.com",

                hashed_password=hash_password(
                    "Staff123!"
                ),

                full_name="SendIt Staff",

                role="staff"

            )

            session.add(
                staff
            )


        session.commit()


        print(
            "Users created successfully!"
        )


if __name__ == "__main__":

    create_users()
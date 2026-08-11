from sqlmodel import SQLModel, create_engine, Session
from dotenv import load_dotenv
import os



# Load variables from .env
load_dotenv()

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL")

# Create database engine
engine = create_engine(
    DATABASE_URL,
    echo=True
)

# Create database tables
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# Provide database session to FastAPI endpoints
def get_session():
    with Session(engine) as session:
        yield session
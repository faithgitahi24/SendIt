import os

from datetime import datetime, timedelta

from dotenv import load_dotenv

from jose import JWTError, jwt

from passlib.context import CryptContext

from fastapi import Depends, HTTPException, status

from fastapi.security import OAuth2PasswordBearer

from sqlmodel import Session, select

from database.session import get_session

from models.user import User

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")

ALGORITHM = os.getenv("ALGORITHM")

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
)

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="login"
)

def hash_password(password: str):
    print("Password received:", repr(password))
    print("Length:", len(password))
    return pwd_context.hash(password)



def verify_password(password, hashed_password):

    return pwd_context.verify(
        password,
        hashed_password
    )


def create_access_token(data: dict):

    to_encode = data.copy()

    expire = datetime.utcnow() + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def decode_access_token(token: str):

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        return payload

    except JWTError:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


def get_current_user(

    token: str = Depends(oauth2_scheme),

    session: Session = Depends(get_session)

):

    payload = decode_access_token(token)

    username = payload.get("sub")

    if username is None:

        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

    user = session.exec(

        select(User).where(
            User.username == username
        )

    ).first()

    if not user:

        raise HTTPException(
            status_code=401,
            detail="User not found"
        )

    if not user.is_active:

        raise HTTPException(
            status_code=403,
            detail="Inactive user"
        )

    return user


def get_current_admin(

    current_user: User = Depends(get_current_user)

):

    if current_user.role != "admin":

        raise HTTPException(
            status_code=403,
            detail="Admin only"
        )

    return current_user


def get_current_manager(

    current_user: User = Depends(get_current_user)

):

    if current_user.role not in ["admin", "manager"]:

        raise HTTPException(
            status_code=403,
            detail="Manager only"
        )

    return current_user
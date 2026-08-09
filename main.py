from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Request
)

from fastapi.security import OAuth2PasswordRequestForm


from sqlmodel import Session, select

from database.session import (
    get_session,
    create_db_and_tables
)

from models.user import (
    User,
    UserCreate,
    UserResponse
)

from models.document import (
    Document,
    DocumentCreate,
    DocumentUpdate
)

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_current_admin,
    get_current_manager
)

from services.weather import get_weather

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

import os
import json
import aiofiles
import httpx

from datetime import datetime
from typing import Optional



app = FastAPI(
    title="SendIt API",
    version="1.0.0"
)

webhooks = []

# Database


@app.on_event("startup")
def startup():
    create_db_and_tables()



# Rate Limiter

limiter = Limiter(
    key_func=get_remote_address
)

app.state.limiter = limiter

app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler
)


# Upload Configuration

UPLOAD_DIR = "uploads"

os.makedirs(
    UPLOAD_DIR,
    exist_ok=True
)

MAX_FILE_SIZE = int(
    os.getenv(
        "MAX_UPLOAD_SIZE",
        5 * 1024 * 1024
    )
)

ALLOWED_EXTENSIONS = [
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".docx"
]


async def notify_webhooks(event_type: str, payload: dict):

    async with httpx.AsyncClient() as client:

        for webhook in webhooks:

            if webhook["event"] == event_type:

                try:

                    await client.post(
                        webhook["url"],
                        json=payload,
                        timeout=5
                    )

                except Exception as e:

                    print(f"Webhook failed: {e}")



# Root Endpoint

@app.get("/")
def home():

    return {
        "message": "Welcome to SendIt Document API"
    }



# Register


@app.post(
    "/register",
    response_model=UserResponse
)
def register(

    user: UserCreate,

    session: Session = Depends(get_session)

):

    existing_user = session.exec(

        select(User).where(

            User.username == user.username

        )

    ).first()

    if existing_user:

        raise HTTPException(

            status_code=400,

            detail="Username already exists"

        )

    existing_email = session.exec(

        select(User).where(

            User.email == user.email

        )

    ).first()

    if existing_email:

        raise HTTPException(

            status_code=400,

            detail="Email already exists"

        )

    new_user = User(

        username=user.username,

        email=user.email,

        hashed_password=hash_password(
            user.password
        ),

        full_name=user.full_name,

        role=user.role

    )

    session.add(new_user)

    session.commit()

    session.refresh(new_user)

    return new_user



# Login


@app.post("/login")
def login(

    form_data: OAuth2PasswordRequestForm = Depends(),

    session: Session = Depends(get_session)

):

    user = session.exec(

        select(User).where(

            User.username == form_data.username

        )

    ).first()

    if not user:

        raise HTTPException(

            status_code=401,

            detail="Invalid username or password"

        )

    if not verify_password(

        form_data.password,

        user.hashed_password

    ):

        raise HTTPException(

            status_code=401,

            detail="Invalid username or password"

        )

    token = create_access_token(

        {

            "sub": user.username

        }

    )

    return {

        "access_token": token,

        "token_type": "bearer"

    }

# Current User


@app.get("/me")
def me(

    current_user: User = Depends(
        get_current_user
    )

):

    return current_user



# FILE VALIDATION


def validate_file(file: UploadFile):

    extension = os.path.splitext(file.filename)[1].lower()

    if extension not in ALLOWED_EXTENSIONS:

        return False, (
            f"File type not allowed. "
            f"Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    return True, ""



# UPLOAD DOCUMENT


@app.post("/documents/upload")
@limiter.limit("10/hour")

async def upload_document(

    request: Request,

    file: UploadFile = File(...),

    city: str = Form(...),

    country: str = Form("Kenya"),

    description: Optional[str] = Form(None),

    current_user: User = Depends(get_current_user),

    session: Session = Depends(get_session)

):

 # Validate extension
  

    valid, message = validate_file(file)

    if not valid:

        raise HTTPException(

            status_code=400,

            detail=message

        )

  
# Read file
   

    contents = await file.read()

    size = len(contents)

    if size > MAX_FILE_SIZE:

        raise HTTPException(

            status_code=400,

            detail="File exceeds maximum size."

        )

   
 # Versioning
   

    existing = session.exec(

        select(Document).where(

            Document.original_filename == file.filename

        )

    ).all()

    version = 1

    if existing:

        version = max(doc.version for doc in existing) + 1

    
    # Safe filename
   

    timestamp = datetime.utcnow().strftime(
        "%Y%m%d%H%M%S"
    )

    filename = (
        f"{timestamp}_"
        f"{current_user.id}_"
        f"{file.filename.replace(' ', '_')}"
    )

    path = os.path.join(

        UPLOAD_DIR,

        filename

    )

    # Save file
  

    async with aiofiles.open(

        path,

        "wb"

    ) as f:

        await f.write(contents)


 # Create database record
  
    document = Document(

        filename=filename,

        original_filename=file.filename,

        version=version,

        file_size=size,

        file_type=file.content_type,

        city=city,

        country=country,

        description=description,

        uploader_id=current_user.id,

        file_path=path,

        status="processing"

    )

    session.add(document)

    session.commit()

    session.refresh(document)


# Weather enrichment
   

    try:

        weather = await get_weather(

            city,

            country

        )

        if weather and "error" not in weather:

            document.weather_data = json.dumps(weather)

            document.weather_fetched_at = datetime.utcnow()

            document.status = "enriched"

        else:

            document.status = "uploaded"

    except Exception as e:

        print(e)

        document.status = "uploaded"

    session.add(document)

    session.commit()

    session.refresh(document)

    return {

        "message": "Document uploaded successfully",

        "document_id": document.id,

        "filename": document.original_filename,

        "version": document.version,

        "status": document.status

    }



# LIST ALL DOCUMENTS


@app.get("/documents")
def get_documents(

    current_user: User = Depends(get_current_user),

    session: Session = Depends(get_session)

):

    if current_user.role == "admin":

        documents = session.exec(
            select(Document)
        ).all()

    else:

        documents = session.exec(

            select(Document).where(

                Document.uploader_id == current_user.id

            )

        ).all()

    return documents


# SEARCH DOCUMENTS

@app.get("/documents/search")
@limiter.limit("20/minute")
def search_documents(
    request: Request,
    q: Optional[str] = None,
    city: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):

    query = select(Document)

    # Staff only see their own documents
    if current_user.role not in ["admin", "manager"]:
        query = query.where(
            Document.uploader_id == current_user.id
        )

    if q:
        query = query.where(
            Document.original_filename.contains(q)
        )

    if city:
        query = query.where(
            Document.city == city
        )

    if status:
        query = query.where(
            Document.status == status
        )

    if date_from:
        query = query.where(
            Document.uploaded_at >= date_from
        )

    if date_to:
        query = query.where(
            Document.uploaded_at <= date_to
        )

    documents = session.exec(query).all()

    return documents




# GET DOCUMENT BY ID


@app.get("/documents/{document_id}")
def get_document(

    document_id: int,

    current_user: User = Depends(get_current_user),

    session: Session = Depends(get_session)

):

    document = session.get(
        Document,
        document_id
    )

    if not document:

        raise HTTPException(

            status_code=404,

            detail="Document not found"

        )

    if (

        current_user.role != "admin"

        and

        document.uploader_id != current_user.id

    ):

        raise HTTPException(

            status_code=403,

            detail="Access denied"

        )

    return document



# UPDATE DOCUMENT


@app.put("/documents/{document_id}")
async def update_document(

    document_id: int,

    document_update: DocumentUpdate,

    current_user: User = Depends(get_current_user),

    session: Session = Depends(get_session)

):

    document = session.get(

        Document,

        document_id

    )

    if not document:

        raise HTTPException(

            status_code=404,

            detail="Document not found"

        )

    if (

        current_user.role != "admin"

        and

        document.uploader_id != current_user.id

    ):

        raise HTTPException(

            status_code=403,

            detail="Access denied"

        )

    update_data = document_update.model_dump(

        exclude_unset=True

    )

    for key, value in update_data.items():

        setattr(

            document,

            key,

            value

        )

    document.updated_at = datetime.utcnow()

    session.add(document)

    session.commit()

    session.refresh(document)

    return {

        "message": "Document updated successfully",

        "document": document

    }



# DELETE DOCUMENT


@app.delete("/documents/{document_id}")
def delete_document(

    document_id: int,

    current_user: User = Depends(get_current_user),

    session: Session = Depends(get_session)

):

    document = session.get(

        Document,

        document_id

    )

    if not document:

        raise HTTPException(

            status_code=404,

            detail="Document not found"

        )

    if (

        current_user.role != "admin"

        and

        document.uploader_id != current_user.id

    ):

        raise HTTPException(

            status_code=403,

            detail="Access denied"

        )

    if os.path.exists(document.file_path):

        os.remove(document.file_path)

    session.delete(document)

    session.commit()

    return {

        "message": "Document deleted successfully"

    }



# ENRICH DOCUMENT

@app.post("/documents/{document_id}/enrich")
@limiter.limit("5/minute")
async def enrich_document(

    request: Request,

    document_id: int,

    current_user: User = Depends(get_current_manager),

    session: Session = Depends(get_session)

):

    document = session.get(Document, document_id)

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    if document.status == "enriched":
        return {
            "message": "Document already enriched"
        }

    weather = await get_weather(
        document.city,
        document.country
    )

    if weather and "error" not in weather:

        document.weather_data = json.dumps(weather)
        document.weather_fetched_at = datetime.utcnow()
        document.status = "enriched"

        session.add(document)
        session.commit()

        await notify_webhooks(
            "document.enriched",
            {
                "document_id": document.id,
                "filename": document.original_filename,
                "status": document.status,
                "city": document.city,
                "country": document.country,
                "uploaded_by": current_user.username
            }
        )

        return {
            "message": "Document enriched successfully",
            "weather": weather
        }

    document.status = "failed"
    session.add(document)
    session.commit()

    raise HTTPException(
        status_code=500,
        detail="Weather enrichment failed"
    )


# GET DOCUMENT WEATHER


@app.get("/documents/{document_id}/weather")
@limiter.limit("10/minute")

def get_document_weather(

    request: Request,

    document_id: int,

    current_user: User = Depends(get_current_user),

    session: Session = Depends(get_session)

):

    document = session.get(

        Document,

        document_id

    )

    if not document:

        raise HTTPException(

            status_code=404,

            detail="Document not found"

        )

    if (

        current_user.role not in [

            "admin",

            "manager"

        ]

        and

        document.uploader_id != current_user.id

    ):

        raise HTTPException(

            status_code=403,

            detail="Access denied"

        )

    if not document.weather_data:

        raise HTTPException(

            status_code=404,

            detail="No weather data available"

        )

    return {

        "document_id": document.id,

        "city": document.city,

        "country": document.country,

        "weather": json.loads(

            document.weather_data

        )

    }




# REGISTER WEBHOOK

@app.post("/webhooks/register")
def register_webhook(
    webhook_url: str = Form(...),
    event_type: str = Form(...),
    current_user: User = Depends(get_current_admin)
):

    webhook = {
        "url": webhook_url,
        "event": event_type
    }

    webhooks.append(webhook)

    return {
        "message": "Webhook registered successfully",
        "webhook": webhook
    }


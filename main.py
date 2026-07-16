"""
PayGam Backend — FastAPI application entrypoint
====================================================
Research Assessment by Ahmed Shabbir Ibrahim Moomin, Colombo, Sri Lanka. I have completed this week’s report, which covers Python, SQL database, 
and security protocols for account members’ fingertip access. However, there are several faults and errors, particularly in the Python coding. Nevertheless, 
I look forward to your feedback and to discussing this further in our weekly meeting.

Run locally:
    uvicorn main:app --reload

Interactive API docs (Swagger UI): http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.database import Base, engine
from app.api.v1.api import api_router

# Import models so they register on Base.metadata before create_all()
from app.models import user, transaction  # noqa: F401

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Backend API for PayGam — e-wallet payments secured by TapSign "
        "(fingerprint biometric authorization) with EGOV identity verification."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to PayGam's actual app/web origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": settings.PROJECT_NAME}

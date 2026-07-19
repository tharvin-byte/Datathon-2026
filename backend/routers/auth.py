"""
AUTH ROUTER — Crime AI Session Initialization
=============================================
POST /auth/login — collects role and district, establishes session_id.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from core.session_store import create_session

router = APIRouter(prefix="/auth", tags=["Auth"])

class LoginRequest(BaseModel):
    role: str = "investigator"
    district: str = "Mysuru"

@router.post("/login")
async def login(payload: LoginRequest):
    session = create_session(payload.role, payload.district)
    return {
        "session_id": session["session_id"],
        "role": session["role"],
        "district": session["district"],
        "status": "active"
    }

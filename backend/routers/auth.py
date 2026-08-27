"""
AUTH ROUTER — Crime AI Session Initialization
=============================================
POST /auth/login — collects role and district, establishes session_id.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from core.session_store import create_session
from core.rbac import normalize_role, role_label, permissions_for

router = APIRouter(prefix="/auth", tags=["Auth"])

class LoginRequest(BaseModel):
    role: str = "investigator"
    rank: str | None = None
    district: str = "Mysuru"

@router.post("/login")
async def login(payload: LoginRequest):
    canonical_role = normalize_role(payload.rank or payload.role)
    session = create_session(canonical_role, payload.district)
    return {
        "session_id": session["session_id"],
        "role": session["role"],
        "rank": session["role"],
        "role_label": role_label(session["role"]),
        "permissions": permissions_for(session["role"]),
        "district": session["district"],
        "status": "active"
    }

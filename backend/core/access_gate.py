"""
ACCESS GATE — Crime AI RBAC & Jurisdictional Gate
=================================================
PURPOSE: Enforces that an officer can only see cases within their jurisdiction
unless they have senior/state-level privileges. Checked BEFORE agents run.
"""

from fastapi import HTTPException
from typing import Dict, Any

def check_access(session: Dict[str, Any], query_text: str) -> None:
    """
    Verify if the officer's role allows querying the requested scope.
    If access is denied, raises an HTTPException (403 Forbidden).
    """
    role = session.get("role", "investigator").lower()
    officer_district = session.get("district", "Mysuru").lower()
    
    # Senior / state-level officers have statewide access
    if role in ["senior", "commissioner", "dgp", "state", "admin"]:
        return

    # Regular investigators are restricted to their home district
    # Check if the query explicitly asks for another district
    query_lower = query_text.lower()
    known_districts = [
        "mysuru", "bengaluru", "hubli", "mangaluru", "dharwad",
        "belagavi", "davangere", "bellary", "shimoga", "gulbarga"
    ]
    
    for dist in known_districts:
        if dist in query_lower and dist != officer_district:
            # If the query asks for another district and officer is only local investigator
            raise HTTPException(
                status_code=403,
                detail=f"Access Gate Denial: Role '{role.title()}' (District: {officer_district.title()}) is not authorized to query records for {dist.title()} jurisdiction."
            )

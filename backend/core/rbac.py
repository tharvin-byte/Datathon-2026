"""KSP Crime AI role and permission policy.

The policy is intentionally centralized so frontend visibility is never the only
security boundary. Existing role values remain accepted through aliases.
"""

from typing import Any, Dict, FrozenSet
from fastapi import HTTPException

ROLE_ALIASES = {
    "admin": "admin",
    "state": "admin",
    "dgp": "admin",
    "commissioner": "senior_officer",
    "senior": "senior_officer",
    "senior_officer": "senior_officer",
    "investigator": "investigator",
    "inspector": "investigator",
    "local_officer": "local_officer",
    "constable": "local_officer",
    "field_officer": "local_officer",
}

ROLE_LABELS = {
    "admin": "Administrator",
    "senior_officer": "Senior Officer",
    "investigator": "Investigator",
    "local_officer": "Local Officer",
}

PERMISSIONS: Dict[str, FrozenSet[str]] = {
    "admin": frozenset({
        "dashboard:view", "investigation:run", "records:view", "records:update",
        "graph:view", "trends:view", "audit:view", "history:view",
        "session:export", "dataset:upload", "agent_status:view",
    }),
    "senior_officer": frozenset({
        "dashboard:view", "investigation:run", "records:view", "graph:view",
        "trends:view", "audit:view", "history:view", "session:export",
        "agent_status:view",
    }),
    "investigator": frozenset({
        "dashboard:view", "investigation:run", "records:view", "graph:view",
        "trends:view", "audit:view", "history:view", "session:export",
        "agent_status:view",
    }),
    "local_officer": frozenset({
        "dashboard:view", "investigation:run", "records:view", "records:update",
        "history:view", "agent_status:view",
    }),
}


def normalize_role(role: Any) -> str:
    """Return a canonical role; unknown values fail closed as local officer."""
    candidate = str(role or "local_officer").strip().lower().replace(" ", "_")
    return ROLE_ALIASES.get(candidate, "local_officer")


def role_label(role: Any) -> str:
    return ROLE_LABELS[normalize_role(role)]


def permissions_for(role: Any) -> list[str]:
    return sorted(PERMISSIONS[normalize_role(role)])


def has_permission(session: Dict[str, Any], permission: str) -> bool:
    role = normalize_role(session.get("role"))
    return permission in PERMISSIONS[role]


def require_permission(session: Dict[str, Any], permission: str) -> None:
    if not has_permission(session, permission):
        role = normalize_role(session.get("role"))
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: {role_label(role)} does not have permission '{permission}'.",
        )


def session_access(session: Dict[str, Any]) -> Dict[str, Any]:
    role = normalize_role(session.get("role"))
    return {
        "role": role,
        "rank": role,
        "role_label": role_label(role),
        "permissions": permissions_for(role),
    }

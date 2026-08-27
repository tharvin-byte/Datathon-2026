"""
SESSION STORE & WEBSOCKET MANAGER — Crime AI Core Module
=========================================================
PURPOSE: In-memory store holding active sessions, blackboard states,
query history, and live WebSocket connections for real-time agent tracking.
"""

from typing import Dict, Any, List
from datetime import datetime
import uuid
from core.rbac import normalize_role, permissions_for, role_label

# In-memory session database
SESSIONS: Dict[str, Dict[str, Any]] = {}
# Active WebSocket connections by session_id
ACTIVE_CONNECTIONS: Dict[str, List[Any]] = {}

def create_session(role: str, district: str) -> Dict[str, Any]:
    """Create a new user session with assigned role and jurisdiction district."""
    session_id = str(uuid.uuid4())[:8]
    canonical_role = normalize_role(role)
    session = {
        "session_id": session_id,
        "role": canonical_role,
        "rank": canonical_role,
        "role_label": role_label(canonical_role),
        "permissions": permissions_for(canonical_role),
        "district": district,
        "created_at": datetime.now().isoformat(),
        "dataset_id": "sample",
        "dataset_metadata": {},
        "conversation_history": [],
        "timeline_events": [],
        "query_results": {},
        "latest_state": {}
    }
    SESSIONS[session_id] = session
    ACTIVE_CONNECTIONS[session_id] = []
    return session

def get_session(session_id: str) -> Dict[str, Any]:
    """Retrieve an active session or raise KeyError/ValueError."""
    if session_id not in SESSIONS:
        # Keep the requested id when the frontend is using the legacy
        # ``default`` session (or when a stale browser session is restored).
        # Previously create_session() generated a different random id here,
        # so upload/query/timeline requests using the same browser id were
        # silently written to different sessions.
        session = create_session("investigator", "Mysuru")
        generated_id = session["session_id"]
        if session_id:
            session["session_id"] = session_id
            SESSIONS.pop(generated_id, None)
            SESSIONS[session_id] = session
            ACTIVE_CONNECTIONS[session_id] = ACTIVE_CONNECTIONS.pop(generated_id, [])
        return session
    return SESSIONS[session_id]

def save_query_result(session_id: str, state: Dict[str, Any], response_json: Dict[str, Any]) -> str:
    """Store the blackboard state and response json for historical/export/dashboard access."""
    session = get_session(session_id)
    query_id = response_json.get("query_id") or str(uuid.uuid4())[:8]
    response_json["query_id"] = query_id
    
    # Store state and response
    session["query_results"][query_id] = {
        "timestamp": datetime.now().isoformat(),
        "state": state,
        "response": response_json
    }
    session["latest_state"] = state
    
    # Update conversation history
    query_text = state.get("resolved_query", "")
    answer_text = response_json.get("answer_text", "")
    if query_text:
        session["conversation_history"].append({"role": "investigator", "text": query_text})
    if answer_text:
        session["conversation_history"].append({"role": "system", "text": answer_text})
        
    return query_id

async def broadcast_status(session_id: str, event_data: Dict[str, Any]):
    """Broadcast real-time progress events over WebSocket to all clients connected to this session."""
    session = get_session(session_id)
    session.setdefault("timeline_events", []).append(event_data)
    connections = ACTIVE_CONNECTIONS.get(session_id, [])
    for ws in list(connections):
        try:
            await ws.send_json(event_data)
        except Exception:
            if ws in connections:
                connections.remove(ws)

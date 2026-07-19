"""
SESSION ROUTER — Crime AI State Retrieval & Export
==================================================
GET /session/{id}/state — serves individual blackboard keys to standalone pages.
GET /sessions — lists past/current sessions.
GET /session/{id}/export — downloads a generated PDF report of the investigation.
"""

import os
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from typing import Optional, List
from core.session_store import get_session, SESSIONS

router = APIRouter(prefix="/session", tags=["Session"])


def _public_state(state: dict) -> dict:
    """Remove runtime-only objects before exposing blackboard state as JSON."""
    public = {
        key: value
        for key, value in state.items()
        if key not in {"dataset", "network_graph"}
    }

    # network_graph is a NetworkX object internally, while the frontend
    # consumes the stable nodes/edges JSON representation.
    graph = state.get("network_graph")
    if graph is not None and hasattr(graph, "nodes") and hasattr(graph, "edges"):
        public["network_graph"] = {
            "nodes": [
                {"id": node, **(metadata or {})}
                for node, metadata in graph.nodes(data=True)
            ],
            "edges": [
                {"source": source, "target": target, **(metadata or {})}
                for source, target, metadata in graph.edges(data=True)
            ],
        }

    return jsonable_encoder(public)

@router.get("/{session_id}/state")
async def get_session_state(
    session_id: str,
    fields: Optional[str] = Query(None, description="Comma-separated state keys to return")
):
    session = get_session(session_id)
    latest_state = session.get("latest_state", {})
    if not latest_state and session.get("query_results"):
        # Grab most recent query state
        last_qid = list(session["query_results"].keys())[-1]
        latest_state = session["query_results"][last_qid].get("state", {})

    public_state = _public_state(latest_state)

    if not fields:
        return public_state

    requested_keys = [k.strip() for k in fields.split(",") if k.strip()]
    result = {}
    for key in requested_keys:
        if key in public_state:
            result[key] = public_state[key]
        elif key == "citations":
            # Map citations from verifier/composer state or final_response
            resp = session.get("query_results", {})
            if resp:
                last_qid = list(resp.keys())[-1]
                result["citations"] = resp[last_qid].get("response", {}).get("citations", [])
            else:
                result["citations"] = public_state.get("citations", [])
        elif key in ["network_edges", "entities_found"] and key not in latest_state:
            # Map from network_graph if present
            ng = public_state.get("network_graph", {})
            if key == "network_edges":
                result["network_edges"] = ng.get("edges", [])
            elif key == "entities_found":
                result["entities_found"] = ng.get("nodes", [])
        else:
            result[key] = None

    return result

@router.get("s")  # GET /sessions when mounted alongside /session
async def list_sessions(session_id: Optional[str] = None):
    sessions_list = []
    for sid, sess in SESSIONS.items():
        query_count = len(sess.get("query_results", {}))
        last_query = ""
        if sess.get("conversation_history"):
            last_query = sess["conversation_history"][-1].get("text", "")[:60]
        sessions_list.append({
            "session_id": sid,
            "role": sess.get("role", "investigator"),
            "district": sess.get("district", "Mysuru"),
            "date": sess.get("created_at", ""),
            "query_count": query_count,
            "summary": last_query or "New Investigation Session"
        })
    return {"sessions": sessions_list}

@router.get("/{session_id}/timeline")
async def get_session_timeline(session_id: str):
    """Serve recorded timeline events for HTTP polling or historical viewing."""
    session = get_session(session_id)
    return {
        "session_id": session_id,
        "events": session.get("timeline_events", [])
    }

@router.get("/{session_id}/export")
async def export_session_pdf(session_id: str):
    """
    Generate and return a PDF report summarizing the investigation results.
    Uses reportlab if installed, or creates a clean formatted HTML/PDF file.
    """
    session = get_session(session_id)
    export_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "exports")
    os.makedirs(export_dir, exist_ok=True)
    pdf_path = os.path.join(export_dir, f"Investigation_Report_{session_id}.pdf")
    
    latest_state = session.get("latest_state", {})
    query_text = latest_state.get("resolved_query", "Multi-Agent Investigation")
    answer_text = latest_state.get("answer_text", "No final response generated.")
    risk = latest_state.get("risk_assessment", {})
    
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1E293B'), spaceAfter=12)
        h2_style = ParagraphStyle('H2Style', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#0F172A'), spaceBefore=10, spaceAfter=6)
        body_style = ParagraphStyle('BodyStyle', parent=styles['BodyText'], fontSize=10, textColor=colors.HexColor('#334155'), spaceAfter=8)
        
        story = [
            Paragraph(f"KSP Crime AI — Official Investigation Report", title_style),
            Paragraph(f"<b>Session ID:</b> {session_id} | <b>Officer District:</b> {session.get('district')} | <b>Role:</b> {session.get('role').title()}", body_style),
            HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#3B82F6'), spaceAfter=15),
            Paragraph("Primary Investigation Subject / Query:", h2_style),
            Paragraph(f"<i>\"{query_text}\"</i>", body_style),
            Spacer(1, 10),
            Paragraph("Executive Summary & AI Synthesis:", h2_style),
            Paragraph(answer_text.replace("\n", "<br/>"), body_style),
            Spacer(1, 10)
        ]
        
        if risk:
            story.append(Paragraph("Risk & Threat Profile:", h2_style))
            story.append(Paragraph(f"<b>Risk Score:</b> {risk.get('score', 0)}/10 | <b>Risk Band:</b> {risk.get('band', 'Low')}", body_style))
            story.append(Paragraph(f"<b>Assessment Basis:</b> {risk.get('explanation', 'N/A')}", body_style))
            
        doc.build(story)
        return FileResponse(pdf_path, filename=f"KSP_Investigation_Report_{session_id}.pdf", media_type="application/pdf")
        
    except ImportError:
        # Fallback if reportlab is not installed: create clear text report with .pdf/txt extension
        txt_path = os.path.join(export_dir, f"Investigation_Report_{session_id}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("=================================================================\n")
            f.write("      KSP CRIME AI — OFFICIAL INVESTIGATION REPORT\n")
            f.write("=================================================================\n\n")
            f.write(f"Session ID:       {session_id}\n")
            f.write(f"Officer District: {session.get('district')}\n")
            f.write(f"Officer Role:     {session.get('role').title()}\n\n")
            f.write("-----------------------------------------------------------------\n")
            f.write(f"SUBJECT QUERY:\n{query_text}\n")
            f.write("-----------------------------------------------------------------\n\n")
            f.write("EXECUTIVE SUMMARY:\n")
            f.write(f"{answer_text}\n\n")
            if risk:
                f.write(f"RISK ASSESSMENT: {risk.get('score', 0)}/10 ({risk.get('band', 'Low')} Band)\n")
                f.write(f"EXPLANATION:     {risk.get('explanation', 'N/A')}\n")
        return FileResponse(txt_path, filename=f"KSP_Investigation_Report_{session_id}.txt", media_type="text/plain")

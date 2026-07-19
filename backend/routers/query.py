"""
QUERY ROUTER — Crime AI Multi-Agent Pipeline Execution
=======================================================
POST /query/text and POST /query/voice — invokes the LangGraph pipeline
and returns the Section 8.2 JSON contract.
"""

import os
import shutil
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import Optional
from graph.pipeline import compiled_graph
from core.access_gate import check_access
from core.session_store import get_session, save_query_result
from core.stt import transcribe_audio
from data.dataset_loader import load_dataset
from routers.dataset import LOADED_DATASETS

router = APIRouter(prefix="/query", tags=["Query"])

class TextQueryRequest(BaseModel):
    session_id: str = "default"
    query_text: str
    language: Optional[str] = "en"
    # Kept optional for compatibility with both /query/text and the legacy
    # /api/investigate adapter. The session's uploaded dataset remains the
    # source of truth when no dataset is supplied.
    dataset: Optional[str] = None

def ensure_session_dataset(session: dict):
    """Ensure session has an active dataset loaded."""
    if "dataset" not in session or not session["dataset"]:
        if "active" in LOADED_DATASETS:
            session["dataset"] = LOADED_DATASETS["active"]
            session["dataset_id"] = "active"
        else:
            ds_id = session.get("dataset_id")
            if ds_id and ds_id in LOADED_DATASETS:
                session["dataset"] = LOADED_DATASETS[ds_id]
            else:
                import glob
                uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "uploads")
                target_path = None
                if os.path.exists(uploads_dir):
                    uploaded_csvs = sorted(glob.glob(os.path.join(uploads_dir, "*.csv")), key=os.path.getmtime, reverse=True)
                    if uploaded_csvs:
                        target_path = uploaded_csvs[0]
                
                if target_path and os.path.exists(target_path):
                    loaded = load_dataset(target_path)
                    LOADED_DATASETS["active"] = loaded
                    session["dataset"] = loaded
                    session["dataset_id"] = "active"
                else:
                    raise HTTPException(status_code=400, detail="No dataset loaded. Please upload a CSV dataset from the Dataset Ingestion tab before running an inquiry.")

@router.post("/text")
async def query_text(payload: TextQueryRequest):
    try:
        session_id = payload.session_id
        query_text = payload.query_text

        session = get_session(session_id)
        if payload.dataset and payload.dataset in LOADED_DATASETS:
            session["dataset_id"] = payload.dataset
            session["dataset"] = LOADED_DATASETS[payload.dataset]
        check_access(session, query_text)  # raises/denies if not permitted
        ensure_session_dataset(session)

        initial_state = {
            "resolved_query": query_text,
            "district_filter": session.get("district", "Mysuru"),
            "dataset_id": session.get("dataset_id", "default"),
            "session_id": session_id,
            "dataset": session["dataset"],
            "conversation_history": session.get("conversation_history", [])
        }

        # compiled_graph is our LangGraph StateGraph / async execution loop
        final_state = await compiled_graph.ainvoke(initial_state)

        response = final_state.get("final_response", {})
        if not response:
            # Fallback formatting if composer output was missing
            response = {
                "session_id": session_id,
                "answer_text": final_state.get("answer_text", "Analysis completed."),
                "citations": final_state.get("citations", []),
                "network_graph": final_state.get("network_graph", {"nodes": [], "edges": []}),
                "trend_findings": final_state.get("trend_findings", []),
                "hotspots": final_state.get("hotspots", []),
                "risk_assessment": final_state.get("risk_assessment", {"score": 0, "band": "Low", "explanation": "No risk data calculated."}),
                "behavioral_profile": final_state.get("behavioral_profile", [])
            }
            
        response["session_id"] = session_id
        response["agents_used"] = final_state.get("agents_used", [])
        response.setdefault("hotspots", final_state.get("hotspots", []))
        verification = final_state.get("verification_result", {})
        response.setdefault("verification_rate", verification.get("verification_rate", 100.0))
        response.setdefault("unsupported_claims", verification.get("unsupported_claims", []))
        
        def make_serializable(obj):
            import numpy as np
            import pandas as pd
            if isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            elif isinstance(obj, (np.bool_, bool)) or type(obj).__name__ in ("bool_", "bool"):
                return bool(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {k: make_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple, set)):
                return [make_serializable(x) for x in obj]
            elif pd.isna(obj):
                return None
            return obj

        response = make_serializable(response)
        save_query_result(session_id, final_state, response)
        return response
    except HTTPException as he:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=he.status_code, content={"detail": he.detail})
    except Exception as e:
        import traceback
        err_msg = f"{type(e).__name__}: {str(e)}"
        traceback.print_exc()
        try:
            with open("scratch_error.log", "w") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"detail": err_msg})

@router.post("/voice")
async def query_voice(
    audio: UploadFile = File(...),
    session_id: str = Form("default")
):
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "audio_temp")
    os.makedirs(upload_dir, exist_ok=True)
    temp_path = os.path.join(upload_dir, f"{uuid.uuid4()}_{audio.filename}")
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)
        
    try:
        transcribed_text, detected_lang = await transcribe_audio(temp_path)
        # Execute pipeline with transcribed text
        payload = TextQueryRequest(session_id=session_id, query_text=transcribed_text, language=detected_lang)
        response = await query_text(payload)
        response["transcribed_query"] = transcribed_text
        response["detected_language"] = detected_lang
        return response
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

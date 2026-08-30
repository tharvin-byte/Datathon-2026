"""
DASHBOARD ROUTER — Crime AI System Summary
==========================================
GET /dashboard/summary?session_id=... — aggregates high-level stats across loaded dataset and queries.
"""

from fastapi import APIRouter, Query
from typing import Optional
import pandas as pd
from core.session_store import get_session, SESSIONS
from core.rbac import require_permission
from routers.dataset import LOADED_DATASETS

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/summary")
async def get_dashboard_summary(session_id: Optional[str] = Query("default")):
    session = get_session(session_id or "default")
    require_permission(session, "dashboard:view")
    dataset = session.get("dataset")
    if not dataset and "active" in LOADED_DATASETS:
        dataset = LOADED_DATASETS["active"]

    total_cases = dataset.get("row_count", 0) if dataset else 0
    
    # Aggregate risk bands across queries
    risk_counts = {"low": 0, "medium": 0, "high": 0}
    if session.get("query_results"):
        for qid, qdata in session["query_results"].items():
            band = qdata.get("state", {}).get("risk_assessment", {}).get("band", "Low").lower()
            if band in risk_counts:
                risk_counts[band] += 1

    # Aggregate monthly trend from dataset df
    monthly_trend = []
    if dataset and "df" in dataset:
        df = dataset["df"]
        if "date" in df.columns:
            try:
                df_date = df.copy()
                df_date["month"] = pd.to_datetime(df_date["date"], errors="coerce").dt.strftime("%b %Y")
                counts = df_date.groupby("month").size().reset_index(name="case_count")
                monthly_trend = counts.to_dict(orient="records")
            except Exception:
                pass

    return {
        "total_cases": total_cases,
        "risk_band_counts": risk_counts,
        "network_graphs_generated": len(session.get("query_results", {})),
        "pending_exports": 0,
        "monthly_trend": monthly_trend
    }

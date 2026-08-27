"""
MAIN FASTAPI APPLICATION — Crime AI Phase 2 Production Server
=============================================================
Mounts all modular routers, configures CORS, pre-loads default datasets,
and serves the static 10-page frontend.
"""

import os
import sys
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Add backend directory to path so imports work cleanly
sys.path.append(os.path.dirname(__file__))

from routers import auth, dataset, query, session, dashboard, ws_status, records
from core.rbac import require_permission
from core.session_store import get_session
from data.dataset_loader import load_dataset
from routers.dataset import LOADED_DATASETS

# Load environment variables if present
_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

app = FastAPI(
    title="KSP Crime AI Investigative Platform API — Datathon 2026",
    description="Multi-Agent Goal-Based Orchestration with Section 8.2 JSON Contract",
    version="2.0.0"
)

# Keep browser access explicit. Same-origin deployment needs no CORS, while local
# development can opt into additional origins with CORS_ORIGINS.
_cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://127.0.0.1:8001,http://localhost:8001").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Include all Phase 2 routers
app.include_router(auth.router)
app.include_router(dataset.router)
app.include_router(query.router)
app.include_router(session.router)
app.include_router(dashboard.router)
app.include_router(ws_status.router)
app.include_router(records.router)

# Pre-load default datasets into memory on startup
@app.on_event("startup")
def startup_event():
    print("Platform initialized with clean empty dataset cache. Ready for custom dataset ingestion.")

# Backward-compatibility API endpoints for earlier frontends/tests
@app.get("/api/datasets")
async def get_datasets_info():
    return {
        k: {
            "record_count": v.get("row_count", len(v.get("df", []))),
            "known_names_count": len(v.get("known_names", []))
        }
        for k, v in LOADED_DATASETS.items()
    }

@app.get("/api/records")
async def get_records(dataset: str = "complex", session_id: str = "default"):
    require_permission(get_session(session_id), "records:view")
    ds_key = dataset
    if ds_key == "complex" and "active" in LOADED_DATASETS:
        ds_key = "active"
    elif ds_key not in LOADED_DATASETS:
        ds_key = "default_complex" if "default_complex" in LOADED_DATASETS else "sample"
    if ds_key not in LOADED_DATASETS:
        raise HTTPException(status_code=500, detail="No dataset loaded.")
        
    df = LOADED_DATASETS[ds_key]["df"]
    records_list = df.fillna("").to_dict(orient="records")
    return {
        "dataset": ds_key,
        "total_count": len(records_list),
        "records": records_list
    }

@app.post("/api/investigate")
async def run_investigate_legacy(payload: dict):
    try:
        from routers.query import TextQueryRequest, query_text
        req = TextQueryRequest(
            session_id=payload.get("session_id", "default"),
            query_text=payload.get("query", ""),
            dataset=payload.get("dataset")
        )
        return await query_text(req)
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

@app.post("/api/dataset/upload")
@app.post("/api/upload")
async def upload_dataset_legacy(
    file: UploadFile = File(...),
    session_id: str = Form("default")
):
    from routers.dataset import upload_dataset
    return await upload_dataset(file=file, session_id=session_id)

# Serve static frontend files (must be mounted last)
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

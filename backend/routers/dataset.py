"""
DATASET ROUTER — Crime AI Dataset Upload & Indexing
====================================================
POST /dataset/upload — multipart file upload handling and embedding generation.
"""

import os
import shutil
import uuid
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from core.session_store import get_session
from data.dataset_loader import load_dataset

router = APIRouter(prefix="/dataset", tags=["Dataset"])

# Store active loaded datasets across sessions
LOADED_DATASETS = {}

@router.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    session_id: str = Form("default")
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV dataset files are supported.")

    clean_filename = os.path.basename(file.filename or "dataset.csv")
    dataset_id = f"ds_{uuid.uuid4().hex[:8]}"
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    
    file_path = os.path.abspath(os.path.join(upload_dir, f"{dataset_id}_{clean_filename}"))
    content = await file.read()
    with open(file_path, "wb") as buffer:
        buffer.write(content)
        
    try:
        loaded = load_dataset(file_path)
        LOADED_DATASETS[dataset_id] = loaded
        LOADED_DATASETS["active"] = loaded
        LOADED_DATASETS["complex"] = loaded
        
        # Attach to session
        session = get_session(session_id)
        session["dataset_id"] = dataset_id
        session["dataset"] = loaded
        session["dataset_metadata"] = {
            "dataset_id": dataset_id,
            "filename": file.filename,
            "row_count": loaded["row_count"],
            "columns": loaded["columns"],
            "has_description_column": loaded["has_description_column"]
        }
        
        return session["dataset_metadata"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load dataset: {str(e)}")

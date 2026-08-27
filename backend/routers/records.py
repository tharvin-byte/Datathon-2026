"""Role-protected crime record read/write operations.

The existing GET /api/records contract remains unchanged. These write endpoints
are additive and operate on the active in-memory dataset used by the current app.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import pandas as pd

from core.access_gate import check_access
from core.rbac import require_permission
from core.session_store import get_session
from data.dataset_loader import embed_texts
from routers.dataset import LOADED_DATASETS

router = APIRouter(prefix="/records", tags=["Records"])

class RecordCreateRequest(BaseModel):
    session_id: str = "default"
    dataset: Optional[str] = None
    record: Dict[str, Any] = Field(min_length=1)

class RecordUpdateRequest(BaseModel):
    session_id: str = "default"
    dataset: Optional[str] = None
    case_id: str = Field(min_length=1, max_length=120)
    updates: Dict[str, Any] = Field(min_length=1)


def _get_dataset(session: dict, requested: Optional[str] = None) -> tuple[str, dict]:
    dataset_id = requested or session.get("dataset_id") or "active"
    if dataset_id == "complex" and "active" in LOADED_DATASETS:
        dataset_id = "active"
    dataset = LOADED_DATASETS.get(dataset_id)
    if not dataset and "active" in LOADED_DATASETS:
        dataset_id, dataset = "active", LOADED_DATASETS["active"]
    if not dataset or "df" not in dataset:
        raise HTTPException(status_code=400, detail="No dataset loaded. An administrator must upload a CSV dataset first.")
    return dataset_id, dataset


def _validate_columns(record: Dict[str, Any], columns: list[str]) -> None:
    unknown = sorted(set(record) - set(columns))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown record column(s): {', '.join(unknown)}")


def _refresh_dataset(dataset: dict) -> None:
    df = dataset["df"]
    dataset["row_count"] = len(df)
    dataset["columns"] = list(df.columns)
    descriptions = df["description"].fillna("").astype(str).tolist() if "description" in df.columns else [""] * len(df)
    dataset["descriptions"] = descriptions
    dataset["desc_embeddings"] = embed_texts(descriptions, fit=True)
    dataset["known_names"] = df["accused_name"].dropna().unique().tolist() if "accused_name" in df.columns else []
    conn = dataset.get("conn")
    if conn is not None:
        df.to_sql("cases", conn, index=False, if_exists="replace")


def _sync_aliases(dataset_id: str, dataset: dict) -> None:
    LOADED_DATASETS[dataset_id] = dataset
    LOADED_DATASETS["active"] = dataset
    LOADED_DATASETS["complex"] = dataset


@router.post("/create")
async def create_record(payload: RecordCreateRequest):
    session = get_session(payload.session_id)
    require_permission(session, "records:update")
    dataset_id, dataset = _get_dataset(session, payload.dataset)
    record = {str(key).strip().lower(): value for key, value in payload.record.items()}
    _validate_columns(record, list(dataset["df"].columns))
    if "case_id" not in record or not str(record["case_id"]).strip():
        raise HTTPException(status_code=422, detail="A non-empty case_id is required.")
    if dataset["df"]["case_id"].astype(str).eq(str(record["case_id"])).any():
        raise HTTPException(status_code=409, detail="A record with this case_id already exists.")
    check_access(session, str(record.get("district", session.get("district", ""))))
    missing = [column for column in dataset["df"].columns if column not in record]
    for column in missing:
        record[column] = None
    dataset["df"] = pd.concat([dataset["df"], pd.DataFrame([record], columns=dataset["df"].columns)], ignore_index=True)
    _refresh_dataset(dataset)
    _sync_aliases(dataset_id, dataset)
    return {"status": "created", "dataset_id": dataset_id, "record": dataset["df"].iloc[-1].fillna("").to_dict()}


@router.post("/update")
async def update_record(payload: RecordUpdateRequest):
    session = get_session(payload.session_id)
    require_permission(session, "records:update")
    dataset_id, dataset = _get_dataset(session, payload.dataset)
    updates = {str(key).strip().lower(): value for key, value in payload.updates.items()}
    _validate_columns(updates, list(dataset["df"].columns))
    df = dataset["df"]
    matches = df.index[df["case_id"].astype(str).eq(payload.case_id)].tolist() if "case_id" in df.columns else []
    if not matches:
        raise HTTPException(status_code=404, detail="Crime record not found.")
    if "district" in updates:
        check_access(session, str(updates["district"]))
    row_index = matches[0]
    for column, value in updates.items():
        if column == "case_id" and str(value) != payload.case_id and df["case_id"].astype(str).eq(str(value)).any():
            raise HTTPException(status_code=409, detail="A record with this case_id already exists.")
        df.at[row_index, column] = value
    _refresh_dataset(dataset)
    _sync_aliases(dataset_id, dataset)
    return {"status": "updated", "dataset_id": dataset_id, "record": df.loc[row_index].fillna("").to_dict()}

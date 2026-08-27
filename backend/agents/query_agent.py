"""
QUERY AGENT (Agent 1) — Crime AI
=================================
PURPOSE: Turn a natural-language question into matching crime records.

TWO PARALLEL PATHS (both always run, results merged):
  1. STRUCTURED PATH — regex/keyword parsing → SQL WHERE clause
     Handles: "crimes in Mysuru last month", "burglary cases in 2026"
     Technique: pattern matching against known column values + dateutil

  2. SEMANTIC PATH — sentence-transformer embeddings → cosine similarity
     Handles: "crimes similar to this MO", "cases involving rear window break-in"
     Technique: all-MiniLM-L6-v2 embeds descriptions at load time,
                query embedded at runtime, top-N by cosine similarity

INPUT:  state["resolved_query"], state["district_filter"]
OUTPUT: state["records_found"] — list of matching record dicts
"""

import re
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil import parser as date_parser

# ---------------------------------------------------------------------------
# Sentence-transformer imports — used for the SEMANTIC path
# We use the lightweight all-MiniLM-L6-v2 model (~80MB) which encodes text
# into 384-dimensional vectors. Cosine similarity between vectors tells us
# how semantically close two pieces of text are.
# ---------------------------------------------------------------------------
def cosine_similarity(X, Y):
    # Normalize X
    norm_X = np.linalg.norm(X, axis=1, keepdims=True)
    norm_X[norm_X == 0] = 1.0
    X_normalized = X / norm_X

    # Normalize Y
    norm_Y = np.linalg.norm(Y, axis=1, keepdims=True)
    norm_Y[norm_Y == 0] = 1.0
    Y_normalized = Y / norm_Y

    return np.dot(X_normalized, Y_normalized.T)

from data.dataset_loader import get_embed_model, embed_texts, load_dataset

# ---------------------------------------------------------------------------
# KNOWN VALUES — used by the structured path's regex parser to identify
# district names, crime types, and time references in the query text.
# In production, these would come from the dataset itself at upload time.
# ---------------------------------------------------------------------------
KNOWN_DISTRICTS = [
    "mysuru", "bengaluru", "hubli", "mangaluru", "dharwad",
    "belagavi", "davangere", "bellary", "shimoga", "gulbarga",
]

KNOWN_CRIME_TYPES = [
    "burglary", "robbery", "theft", "assault", "murder",
    "cybercrime", "drug trafficking", "chain snatching",
    "kidnapping", "fraud", "extortion",
]

# Relative time phrases → timedelta mappings
TIME_PATTERNS = {
    r"last\s+week": timedelta(weeks=1),
    r"last\s+month": timedelta(days=30),
    r"last\s+(\d+)\s+days?": None,  # handled dynamically
    r"last\s+(\d+)\s+months?": None,
    r"this\s+month": timedelta(days=30),
    r"this\s+week": timedelta(weeks=1),
    r"past\s+week": timedelta(weeks=1),
    r"past\s+month": timedelta(days=30),
    r"recent": timedelta(days=14),
}


# ===================================================================
# PATH 1: STRUCTURED — extract filters from natural language → SQL
# ===================================================================
# Technique: regex + keyword matching against known column values.
# This is NOT an LLM call — it's deterministic pattern matching.
# ===================================================================

def extract_district(query_lower: str) -> str | None:
    """Check if any known district name appears in the query."""
    for district in KNOWN_DISTRICTS:
        # Word boundary match to avoid partial matches
        if re.search(rf"\b{district}\b", query_lower):
            return district.title()  # "mysuru" → "Mysuru"
    return None


def extract_crime_type(query_lower: str) -> str | None:
    """Check if any known crime type appears in the query."""
    for crime in KNOWN_CRIME_TYPES:
        if re.search(rf"\b{crime}\b", query_lower):
            return crime.title()
    return None


def extract_date_range(query_lower: str) -> tuple[str, str] | None:
    """
    Parse relative time expressions into (start_date, end_date) strings.
    
    Examples:
      "last month"     → (30 days ago, today)
      "last 10 days"   → (10 days ago, today)
      "last 3 months"  → (90 days ago, today)
    
    Technique: regex captures the time phrase, dateutil/timedelta
    computes the actual date range. No LLM needed.
    """
    today = datetime.now()

    # Handle "last N days"
    match = re.search(r"last\s+(\d+)\s+days?", query_lower)
    if match:
        days = int(match.group(1))
        start = today - timedelta(days=days)
        return (start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))

    # Handle "last N months"
    match = re.search(r"last\s+(\d+)\s+months?", query_lower)
    if match:
        months = int(match.group(1))
        start = today - timedelta(days=months * 30)
        return (start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))

    # Handle fixed phrases like "last week", "last month", "recent"
    for pattern, delta in TIME_PATTERNS.items():
        if delta is not None and re.search(pattern, query_lower):
            start = today - delta
            return (start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))

    # Handle explicit dates like "from 2026-06-01 to 2026-07-01"
    match = re.search(
        r"from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})",
        query_lower,
    )
    if match:
        return (match.group(1), match.group(2))

    return None


def extract_accused_name(query_lower: str, known_names: list[str]) -> str | None:
    """Check if any known accused name appears in the query."""
    for name in known_names:
        if name.lower() in query_lower:
            return name
    return None


def build_sql_query(
    district: str | None,
    crime_type: str | None,
    date_range: tuple[str, str] | None,
    accused_name: str | None,
    district_filter: str | None,
) -> tuple[str, list]:
    """
    Build a SQL WHERE clause from extracted filters.
    
    Technique: dynamic SQL construction with parameterized queries
    to prevent injection. Each filter adds an AND condition.
    
    The district_filter (from the access gate / RBAC) is ALWAYS applied
    to enforce jurisdictional access control.
    """
    conditions = []
    params = []

    # RBAC filter — always applied, non-negotiable
    if district_filter:
        conditions.append("LOWER(district) = LOWER(?)")
        params.append(district_filter)

    # User-requested district (only if different from RBAC filter)
    if district and (not district_filter or district.lower() != district_filter.lower()):
        conditions.append("LOWER(district) = LOWER(?)")
        params.append(district)

    if crime_type:
        conditions.append("LOWER(crime_type) = LOWER(?)")
        params.append(crime_type)

    if date_range:
        conditions.append("date >= ? AND date <= ?")
        params.extend(date_range)

    if accused_name:
        conditions.append("LOWER(accused_name) = LOWER(?)")
        params.append(accused_name)

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"SELECT * FROM cases WHERE {where}"
    return sql, params


# ===================================================================
# PATH 2: SEMANTIC — embed query → cosine similarity vs descriptions
# ===================================================================
# Technique: sentence-transformers converts text into dense vectors.
# Cosine similarity measures how "close" two texts are in meaning.
# This catches things SQL can't — "cases with rear window entry" will
# match descriptions mentioning "broke in through the rear window"
# even though there's no "rear_window" column.
# ===================================================================

# ===================================================================
# Note: embed_texts and load_dataset are imported from data.dataset_loader
# ===================================================================

def semantic_search(
    query_text: str,
    descriptions: list[str],
    description_embeddings: np.ndarray,
    top_n: int = 5,
    threshold: float = 0.25,
) -> list[int]:
    """
    Find the top-N records whose description is most semantically
    similar to the query.
    
    Returns: list of row indices (into the descriptions list) that
    exceed the similarity threshold, sorted by relevance.
    
    Technique:
      1. Embed the query text → 384-dim vector
      2. Compute cosine similarity against all pre-embedded descriptions
      3. Filter by threshold (ignore very weak matches)
      4. Return top-N indices sorted by similarity score
    """
    query_embedding = get_embed_model().encode([query_text], show_progress_bar=False)
    similarities = cosine_similarity(query_embedding, description_embeddings)[0]

    # Get indices where similarity exceeds threshold
    candidates = [
        (idx, score)
        for idx, score in enumerate(similarities)
        if score >= threshold
    ]
    # Sort by similarity descending, take top N
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [idx for idx, _ in candidates[:top_n]]


# ===================================================================
# MAIN FUNCTION — the query_agent entry point
# ===================================================================
# This is what the planner calls. It reads from state, runs both
# paths, merges results, and writes back to state.
# ===================================================================

def query_agent(state: dict) -> dict:
    """
    Query Agent — fetch matching crime records.
    
    Reads:  state["resolved_query"]   — the investigator's question
            state["district_filter"]  — RBAC jurisdictional filter
            state["dataset"]          — loaded dataset (from load_dataset)
    
    Writes: state["records_found"]    — list of matching record dicts
            state["query_method"]     — which paths found results (for audit)
    
    TECHNIQUE SUMMARY:
      1. Parse query text with regex to extract structured filters
      2. Build and execute SQL query (structured path)
      3. Embed query and run cosine similarity (semantic path)
      4. Merge both result sets, deduplicate by case_id
      5. Write merged results to state
    """
    query_text = state["resolved_query"]
    district_filter = state.get("district_filter")
    dataset = state["dataset"]

    query_lower = query_text.lower()
    conn = dataset["conn"]
    df = dataset["df"]

    methods_used = []

    # ----- PATH 1: STRUCTURED -----
    district = extract_district(query_lower)
    crime_type = extract_crime_type(query_lower)
    date_range = extract_date_range(query_lower)
    accused_name = extract_accused_name(query_lower, dataset["known_names"])

    sql, params = build_sql_query(
        district, crime_type, date_range, accused_name, district_filter
    )

    print(f"[QueryAgent] Structured path — SQL: {sql}")
    print(f"[QueryAgent] Structured path — Params: {params}")

    cursor = conn.execute(sql, params)
    columns = [desc[0] for desc in cursor.description]
    structured_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    if structured_rows:
        methods_used.append("structured_sql")
    print(f"[QueryAgent] Structured path found {len(structured_rows)} records")

    # ----- PATH 2: SEMANTIC -----
    semantic_indices = semantic_search(
        query_text,
        dataset["descriptions"],
        dataset["desc_embeddings"],
        top_n=5,
        threshold=0.25,
    )

    semantic_rows = []
    for idx in semantic_indices:
        row = df.iloc[idx].to_dict()
        # Convert any NaN to None for clean JSON later
        row = {k: (None if pd.isna(v) else v) for k, v in row.items()}
        semantic_rows.append(row)

    if semantic_rows:
        methods_used.append("semantic_similarity")
    print(f"[QueryAgent] Semantic path found {len(semantic_rows)} records")

    # ----- MERGE & DEDUPLICATE -----
    # Combine both result sets, remove duplicates by case_id
    seen_ids = set()
    merged = []

    # Structured results first (higher confidence for exact matches)
    for row in structured_rows:
        cid = row.get("case_id")
        if cid not in seen_ids:
            seen_ids.add(cid)
            row["_match_source"] = "structured"
            merged.append(row)

    # Then semantic results (adds meaning-based matches)
    for row in semantic_rows:
        cid = row.get("case_id")
        if cid not in seen_ids:
            seen_ids.add(cid)
            row["_match_source"] = "semantic"
            merged.append(row)
        elif cid in seen_ids:
            # Already found by structured — mark as both
            for m in merged:
                if m.get("case_id") == cid:
                    m["_match_source"] = "both"

    print(f"[QueryAgent] Merged total: {len(merged)} unique records")

    # ----- WRITE TO STATE -----
    state["records_found"] = merged
    state["query_method"] = methods_used
    state["structured_filters"] = {
        "district": district,
        "crime_type": crime_type,
        "date_range": date_range,
        "accused_name": accused_name,
    }

    return state

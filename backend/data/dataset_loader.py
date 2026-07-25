"""
DATASET LOADER — Crime AI Data Module
=====================================
PURPOSE: Loads uploaded CSV datasets into pandas DataFrame, SQLite table,
and builds TF-IDF vector representations for instant semantic similarity search.
"""

import os
import sqlite3
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

def embed_texts(texts: list[str]) -> np.ndarray:
    """Encode a list of texts into normalized TF-IDF vectors."""
    if not texts or all(len(str(t).strip()) == 0 for t in texts):
        return np.zeros((len(texts), 1))
    texts_clean = [str(t) for t in texts]
    vectorizer = TfidfVectorizer(stop_words='english', max_features=500)
    try:
        tfidf_matrix = vectorizer.fit_transform(texts_clean)
        return normalize(tfidf_matrix).toarray()
    except Exception:
        return np.zeros((len(texts), 1))

class TFIDFEmbedder:
    def encode(self, texts, show_progress_bar=False):
        return embed_texts(texts)

def get_embed_model():
    """Backward-compatible helper returning a lightweight TF-IDF embedder."""
    return TFIDFEmbedder()

def load_dataset(csv_path: str) -> dict:
    """
    Load the CSV into:
      1. An in-memory SQLite database (for structured queries)
      2. A pandas DataFrame (for easy row access)
      3. Pre-computed description TF-IDF embeddings (for fast semantic search)
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Dataset CSV not found at {csv_path}")

    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower() for c in df.columns]

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    df.to_sql("cases", conn, index=False, if_exists="replace")

    descriptions = df["description"].fillna("").tolist() if "description" in df.columns else [""] * len(df)
    desc_embeddings = embed_texts(descriptions)
    known_names = df["accused_name"].dropna().unique().tolist() if "accused_name" in df.columns else []

    return {
        "conn": conn,
        "df": df,
        "descriptions": descriptions,
        "desc_embeddings": desc_embeddings,
        "known_names": known_names,
        "has_description_column": "description" in df.columns,
        "columns": list(df.columns),
        "row_count": len(df)
    }

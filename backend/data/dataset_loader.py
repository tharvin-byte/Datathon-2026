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
import re

STOP_WORDS = {
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 'any', 'are', "aren't", 'as', 'at',
    'be', 'because', 'been', 'before', 'being', 'below', 'between', 'both', 'but', 'by', "can't", 'cannot', 'could',
    "couldn't", 'did', "didn't", 'do', 'does', "doesn't", 'doing', "don't", 'down', 'during', 'each', 'few', 'for',
    'from', 'further', 'had', "hadn't", 'has', "hasn't", 'have', "haven't", 'having', 'he', "he'd", "he'll", "he's",
    'her', 'here', "here's", 'hers', 'herself', 'him', 'himself', 'his', 'how', "how's", 'i', "i'd", "i'll", "i'm",
    "i've", 'if', 'in', 'into', 'is', "isn't", 'it', "it's", 'its', 'itself', "let's", 'me', 'more', 'most', "mustn't",
    'my', 'myself', 'no', 'nor', 'not', 'of', 'off', 'on', 'once', 'only', 'or', 'other', 'ought', 'our', 'ours',
    'ourselves', 'out', 'over', 'own', 'same', "shan't", 'she', "she'd", "she'll", "she's", 'should', "shouldn't",
    'so', 'some', 'such', 'than', 'that', "that's", 'the', 'their', 'theirs', 'them', 'themselves', 'then', 'there',
    "there's", 'these', 'they', "they'd", "they'll", "they're", "they've", 'this', 'those', 'through', 'to', 'too',
    'under', 'until', 'up', 'very', 'was', "wasn't", 'we', "we'd", "we'll", "we're", "we've", 'were', "weren't",
    'what', "what's", 'when', "when's", 'where', "where's", 'which', 'while', 'who', "who's", 'whom', 'why', "why's",
    'with', "won't", 'would', "wouldn't", 'you', "you'd", "you'll", "you're", "you've", 'your', 'yours', 'yourself',
    'yourselves'
}

class SimpleTfidfVectorizer:
    def __init__(self, stop_words='english', max_features=1000):
        self.stop_words = stop_words
        self.max_features = max_features
        self.vocabulary_ = {}
        self.idf_ = []
        self.feature_names_ = []

    def _tokenize(self, text):
        words = re.findall(r'\b\w\w+\b', str(text).lower())
        if self.stop_words == 'english':
            words = [w for w in words if w not in STOP_WORDS]
        return words

    def fit_transform(self, raw_documents):
        tokenized_docs = [self._tokenize(doc) for doc in raw_documents]
        n_samples = len(raw_documents)

        term_df = {}
        term_tf = {}
        for doc in tokenized_docs:
            seen_in_doc = set()
            for term in doc:
                term_tf[term] = term_tf.get(term, 0) + 1
                if term not in seen_in_doc:
                    term_df[term] = term_df.get(term, 0) + 1
                    seen_in_doc.add(term)

        sorted_terms = sorted(term_tf.keys(), key=lambda t: (term_tf[t], term_df[t]), reverse=True)
        if self.max_features is not None:
            sorted_terms = sorted_terms[:self.max_features]

        self.vocabulary_ = {term: idx for idx, term in enumerate(sorted_terms)}
        self.feature_names_ = sorted_terms

        self.idf_ = []
        for term in sorted_terms:
            df = term_df.get(term, 0)
            idf_val = np.log((1.0 + n_samples) / (1.0 + df)) + 1.0
            self.idf_.append(idf_val)
        self.idf_ = np.array(self.idf_)

        return self.transform(raw_documents)

    def transform(self, raw_documents):
        n_samples = len(raw_documents)
        n_features = len(self.vocabulary_)
        if n_features == 0:
            return np.zeros((n_samples, 1))

        tf_matrix = np.zeros((n_samples, n_features))
        for row_idx, doc in enumerate(raw_documents):
            words = self._tokenize(doc)
            for word in words:
                if word in self.vocabulary_:
                    col_idx = self.vocabulary_[word]
                    tf_matrix[row_idx, col_idx] += 1

        tfidf_matrix = tf_matrix * self.idf_

        norms = np.linalg.norm(tfidf_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return tfidf_matrix / norms

_ACTIVE_VECTORIZER = None

def embed_texts(texts: list[str], fit: bool = False) -> np.ndarray:
    """Encode a list of texts into normalized TF-IDF vectors."""
    global _ACTIVE_VECTORIZER
    if not texts or all(len(str(t).strip()) == 0 for t in texts):
        n_cols = _ACTIVE_VECTORIZER.transform(["test"]).shape[1] if _ACTIVE_VECTORIZER else 1
        return np.zeros((len(texts), n_cols))
    
    texts_clean = [str(t) for t in texts]
    
    if fit or _ACTIVE_VECTORIZER is None:
        _ACTIVE_VECTORIZER = SimpleTfidfVectorizer(stop_words='english', max_features=1000)
        try:
            return _ACTIVE_VECTORIZER.fit_transform(texts_clean)
        except Exception:
            _ACTIVE_VECTORIZER = None
            return np.zeros((len(texts), 1))
    else:
        try:
            return _ACTIVE_VECTORIZER.transform(texts_clean)
        except Exception:
            n_cols = _ACTIVE_VECTORIZER.transform(["test"]).shape[1] if _ACTIVE_VECTORIZER else 1
            return np.zeros((len(texts), n_cols))


class TFIDFEmbedder:
    def encode(self, texts, show_progress_bar=False):
        return embed_texts(texts, fit=False)

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
    desc_embeddings = embed_texts(descriptions, fit=True)
    known_names = df["accused_name"].dropna().unique().tolist() if "accused_name" in df.columns else []

    return {
        "conn": conn,
        "df": df,
        "descriptions": descriptions,
        "desc_embeddings": desc_embeddings,
        "known_names": known_names,
        "has_description_column": "description" in df.columns,
        "columns": list(df.columns),
        "row_count": len(df),
        "source_path": os.path.abspath(csv_path)
    }

"""
TREND AGENT (Agent 3) — Crime AI
==================================
PURPOSE: Analyze crime records over time and location to spot patterns,
spikes, and trends that an investigator should know about.

TWO MECHANISMS (both always run):

  1. STRUCTURED STATS — group records by location × crime_type × month,
     compute period-over-period change (pct_change) and rolling averages
     to distinguish real trends from one-off spikes.
     Technique: pandas groupby + pct_change + rolling mean

  2. MO PATTERN SCAN — for each detected spike, scan the descriptions
     of cases within that window to find what's common — e.g. "rear
     window entry" appearing in 4 of 5 burglary cases in the spike.
     Technique: keyword frequency counting (lightweight TF-IDF approach)

INPUT:  state["records_found"] (from Query Agent)
OUTPUT: state["trend_findings"]       — list of trend/spike findings
        state["demographic_findings"] — breakdown by demographics if available

DEPENDENCY: Runs AFTER Query Agent. Can run IN PARALLEL with Link Agent.
"""

import re
from collections import Counter
from datetime import datetime

import pandas as pd


# ===================================================================
# MECHANISM 1: STRUCTURED TIME/LOCATION STATS
# ===================================================================
# Group crimes by (location, crime_type, month), count them, and
# compare periods. A >=25% increase flags as a "finding."
#
# Why rolling average? A single month might spike due to a reporting
# backlog or one big bust. A 3-month rolling average smooths that
# out — if the rolling average is ALSO rising, the trend is real.
# ===================================================================

SPIKE_THRESHOLD = 0.25  # 25% increase flags as notable


def compute_time_trends(df: pd.DataFrame) -> list[dict]:
    """
    Group by location × crime_type × month, compute:
      - Raw count per period
      - Period-over-period percent change
      - 3-period rolling average
      - Flag anything with >= 25% increase as a finding
    """
    findings = []

    if df.empty or "date" not in df.columns:
        return findings

    # Ensure date is datetime
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    if df.empty:
        return findings

    # Create a month column for grouping
    df["month"] = df["date"].dt.to_period("M")

    # --- Group by location × crime_type × month ---
    # This gives us counts like: Mysuru × Burglary × 2026-06 = 3 cases
    group_cols = []
    if "district" in df.columns:
        group_cols.append("district")
    if "crime_type" in df.columns:
        group_cols.append("crime_type")
    group_cols.append("month")

    if len(group_cols) < 2:
        # Not enough columns to do meaningful grouping
        return findings

    grouped = df.groupby(group_cols).size().reset_index(name="case_count")

    # --- For each (location, crime_type) pair, analyze the time series ---
    id_cols = [c for c in group_cols if c != "month"]

    for keys, subset in grouped.groupby(id_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)

        subset = subset.sort_values("month")

        if len(subset) < 2:
            # Can't compute change with just one period — still report
            # the count as a baseline finding
            row = subset.iloc[0]
            findings.append({
                "location": keys[0] if len(keys) > 0 else "All",
                "crime_type": keys[1] if len(keys) > 1 else "All",
                "period": str(row["month"]),
                "case_count": int(row["case_count"]),
                "pct_change": None,
                "rolling_avg": None,
                "is_spike": False,
                "trend_direction": "baseline",
            })
            continue

        # Percent change between consecutive months
        subset = subset.copy()
        subset["pct_change"] = subset["case_count"].pct_change()

        # 3-period rolling average (or less if fewer periods)
        window = min(3, len(subset))
        subset["rolling_avg"] = (
            subset["case_count"].rolling(window=window, min_periods=1).mean()
        )

        # Check the most recent period for spikes
        latest = subset.iloc[-1]
        pct = latest["pct_change"] if pd.notna(latest["pct_change"]) else 0

        is_spike = pct >= SPIKE_THRESHOLD
        if pct > 0:
            direction = "increasing"
        elif pct < 0:
            direction = "decreasing"
        else:
            direction = "stable"

        findings.append({
            "location": keys[0] if len(keys) > 0 else "All",
            "crime_type": keys[1] if len(keys) > 1 else "All",
            "period": str(latest["month"]),
            "case_count": int(latest["case_count"]),
            "pct_change": round(float(pct * 100), 1) if pd.notna(pct) else None,
            "rolling_avg": round(float(latest["rolling_avg"]), 1),
            "is_spike": is_spike,
            "trend_direction": direction,
        })

    return findings


# ===================================================================
# LOCATION HOTSPOT DETECTION
# ===================================================================
# Count crimes per location to find hotspots — simple but useful.
# ===================================================================

def detect_hotspots(df: pd.DataFrame) -> list[dict]:
    """Find locations with the highest crime concentration."""
    if df.empty or "district" not in df.columns:
        return []

    location_counts = df["district"].value_counts()
    total = len(df)

    hotspots = []
    for location, count in location_counts.items():
        hotspots.append({
            "location": location,
            "case_count": int(count),
            "percentage": round(count / total * 100, 1),
        })

    return hotspots


# ===================================================================
# MECHANISM 2: MO PATTERN SCAN (within detected spikes)
# ===================================================================
# For each spike, read the descriptions of cases in that window and
# find common keywords/phrases — this tells the investigator WHAT
# kind of crime is driving the numbers, not just THAT numbers are up.
#
# Technique: simple keyword frequency counting. We split descriptions
# into words, filter out common stopwords, and find the most frequent
# terms across the spike's cases. This is a lightweight version of
# TF-IDF — good enough for a hackathon, fully deterministic, no LLM.
# ===================================================================

STOPWORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
    "was", "were", "is", "are", "been", "be", "has", "had", "have", "from",
    "with", "by", "that", "this", "it", "its", "not", "but", "as", "he",
    "she", "his", "her", "they", "them", "their", "who", "whom", "which",
    "what", "where", "when", "how", "no", "yes", "do", "did", "does",
    "will", "would", "could", "should", "may", "might", "can", "shall",
    "about", "into", "over", "after", "before", "between", "under",
    "during", "through", "above", "below", "up", "down", "out",
    "than", "then", "so", "if", "also", "very", "just", "being",
    "same", "each", "other", "some", "such", "more", "most",
}


def extract_mo_patterns(records: list[dict], location: str = None,
                        crime_type: str = None) -> list[str]:
    """
    Scan descriptions of records matching the spike criteria.
    Return the top recurring phrases/keywords that describe the MO.
    """
    # Filter records to only those in the spike window
    relevant = records
    if location:
        relevant = [
            r for r in relevant
            if (r.get("district") or "").lower() == location.lower()
        ]
    if crime_type:
        relevant = [
            r for r in relevant
            if (r.get("crime_type") or "").lower() == crime_type.lower()
        ]

    if not relevant:
        return []

    # Collect all words from descriptions
    all_words = []
    # Also collect 2-word phrases (bigrams) for more meaningful patterns
    all_bigrams = []

    for record in relevant:
        desc = (record.get("description") or "").lower()
        # Clean: remove punctuation except hyphens
        desc = re.sub(r"[^\w\s-]", " ", desc)
        words = [w for w in desc.split() if w not in STOPWORDS and len(w) > 2]
        all_words.extend(words)

        # Generate bigrams (consecutive word pairs)
        for i in range(len(words) - 1):
            all_bigrams.append(f"{words[i]} {words[i+1]}")

    # Find most common terms
    word_counts = Counter(all_words).most_common(10)
    bigram_counts = Counter(all_bigrams).most_common(5)

    # Build pattern descriptions
    patterns = []
    for bigram, count in bigram_counts:
        if count >= 2:  # Appears in at least 2 cases
            patterns.append(f'"{bigram}" (mentioned in {count} cases)')

    for word, count in word_counts:
        if count >= 2 and len(patterns) < 8:
            patterns.append(f'"{word}" (mentioned {count} times)')

    return patterns


# ===================================================================
# DEMOGRAPHIC BREAKDOWN (if columns exist)
# ===================================================================
# If the dataset has columns like age, gender, employment_status,
# break down crimes by those demographics.
# ===================================================================

def compute_demographics(df: pd.DataFrame) -> list[dict]:
    """
    If demographic columns exist, compute breakdowns.
    Returns empty list if no demographic data is available.
    """
    demo_cols = []
    for col in ["age_bracket", "gender", "employment_status", "age", "sex"]:
        if col in df.columns:
            demo_cols.append(col)

    if not demo_cols or "crime_type" not in df.columns:
        return []

    findings = []
    for col in demo_cols:
        breakdown = (
            df.groupby(["crime_type", col])
            .size()
            .reset_index(name="count")
        )
        for _, row in breakdown.iterrows():
            findings.append({
                "crime_type": row["crime_type"],
                col: row[col],
                "count": int(row["count"]),
            })

    return findings


# ===================================================================
# MAIN FUNCTION — the trend_agent entry point
# ===================================================================

def trend_agent(state: dict) -> dict:
    """
    Trend Agent — spot patterns over time and location.

    Reads:  state["records_found"] — records from Query Agent

    Writes: state["trend_findings"]       — list of trend/spike findings
            state["demographic_findings"] — breakdown by demographics
            state["hotspots"]             — location concentration data
            state["mo_patterns"]          — common MO keywords in spikes

    TECHNIQUE SUMMARY:
      1. Load records into pandas DataFrame
      2. Group by location × crime_type × month
      3. Compute pct_change and rolling averages
      4. Flag spikes (>=25% increase)
      5. For each spike, scan descriptions for common MO keywords
      6. Compute hotspots and demographics if data available
    """
    records = state.get("records_found", [])

    if not records:
        state["trend_findings"] = []
        state["demographic_findings"] = []
        state["hotspots"] = []
        state["mo_patterns"] = {}
        print("[TrendAgent] No records to process.")
        return state

    print(f"[TrendAgent] Processing {len(records)} records...")

    # Convert records to DataFrame
    df = pd.DataFrame(records)

    # --- Step 1: Time-based trends ---
    trend_findings = compute_time_trends(df)
    spike_count = sum(1 for f in trend_findings if f.get("is_spike"))
    print(f"[TrendAgent] Found {len(trend_findings)} trend data points, {spike_count} spikes")

    # --- Step 2: MO pattern scan for each spike ---
    mo_patterns = {}
    for finding in trend_findings:
        if finding.get("is_spike"):
            key = f"{finding['location']}_{finding['crime_type']}"
            patterns = extract_mo_patterns(
                records,
                location=finding["location"],
                crime_type=finding["crime_type"],
            )
            if patterns:
                mo_patterns[key] = patterns
                finding["mo_patterns"] = patterns
                print(
                    f"[TrendAgent] MO patterns for {key}: {patterns[:3]}"
                )

    # --- Step 3: Hotspot detection ---
    hotspots = detect_hotspots(df)
    print(f"[TrendAgent] Hotspots: {[(h['location'], h['case_count']) for h in hotspots[:3]]}")

    # --- Step 4: Demographic breakdown ---
    demographic_findings = compute_demographics(df)

    # --- Write to state ---
    state["trend_findings"] = trend_findings
    state["demographic_findings"] = demographic_findings
    state["hotspots"] = hotspots
    state["mo_patterns"] = mo_patterns

    print(f"[TrendAgent] Done. {len(trend_findings)} findings written to state.")

    return state

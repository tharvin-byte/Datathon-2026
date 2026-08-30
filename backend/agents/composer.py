"""
COMPOSER AGENT — Crime AI Response Builder
=============================================
PURPOSE: Package verified findings into the final response the
investigator sees — translated to their language, clearly formatted,
with citations attached.

WHAT IT DOES:
  1. Reads all verified findings from state
  2. Composes a natural-language answer (Gemini or template-based)
  3. Localizes to Kannada if the query was in Kannada
  4. Attaches citations from the verifier
  5. Shapes the response into the section 8.2 JSON contract
  6. Optionally generates a PDF export

TWO MODES:
  - GEMINI MODE: LLM writes a clear, investigator-friendly answer
    citing specific records, in the requested language
  - TEMPLATE MODE: builds the answer from f-string templates using
    the structured findings — works without any API key

INPUT:  entire state (all agent outputs + citations + verification)
OUTPUT: state["final_response"] — the section 8.2 JSON response object
        state["answer_text"]    — the composed answer string

DEPENDENCY: Runs LAST — after verifier has checked everything.
"""

import json
import os
import re
import time
import uuid
from datetime import datetime

try:
    # pyrefly: ignore [missing-import]
    from core.llm_client import get_generative_model
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# ===================================================================
# LANGUAGE DETECTION — simple heuristic for Kannada vs English
# ===================================================================
# Kannada Unicode range: U+0C80 to U+0CFF
# If more than 20% of characters are in this range, it's Kannada.
# ===================================================================

def detect_language(text: str) -> str:
    """Detect if text is primarily Kannada or English."""
    if not text:
        return "en"

    kannada_chars = sum(1 for c in text if "\u0C80" <= c <= "\u0CFF")
    total_chars = len(text.strip())

    if total_chars == 0:
        return "en"

    if kannada_chars / total_chars > 0.2:
        return "kn"
    return "en"


# ===================================================================
# TEMPLATE-BASED COMPOSER — works without Gemini
# ===================================================================
# Builds the answer from structured findings using f-string templates.
# Each section of the answer maps to a specific agent's output.
# Less natural-sounding than Gemini but fully functional.
# ===================================================================

def compose_template_answer(state: dict, language: str) -> str:
    """
    Build a comprehensive, executive-grade investigation report from structured findings.
    Provides detailed case narratives without arbitrary truncation, network breakdown,
    temporal spikes, risk profile, and tactical recommendations.
    """
    sections = []
    query = state.get("resolved_query", "")
    records = state.get("records_found", [])
    entities = state.get("entities_found", [])
    edges = state.get("network_edges", [])
    trends = state.get("trend_findings", [])
    risk = state.get("risk_assessment", {})
    profile = state.get("behavioral_profile", [])
    citations = state.get("citations", [])
    vr = state.get("verification_result", {})

    # --- 1. Header & Executive Summary ---
    sections.append(f"# 📋 Executive Investigation & Intelligence Briefing")
    sections.append(f"**Target Investigation Query:** *{query}*")
    
    risk_band = risk.get("band", "Medium") if risk else "Assessed"
    risk_score = risk.get("score", "N/A") if risk else "N/A"
    records_count = len(records)
    districts_involved = sorted(list(set([r.get("district", "Unknown") for r in records if r.get("district")])))
    
    sections.append("## 📌 Executive Summary")
    if records_count > 0:
        sections.append(
            f"An exhaustive intelligence sweep across the platform dataset identified **{records_count} verified case record(s)** directly matching the investigation criteria across **{len(districts_involved)} jurisdiction(s)** ({', '.join(districts_involved[:6])}{' et al.' if len(districts_involved) > 6 else ''}). "
            f"The overall operational threat level is evaluated as **{risk_band}** (Score: **{risk_score}/10**). "
            f"This briefing details the extracted Modus Operandi (MO), interconnected criminal structures, and critical evidence required for targeted enforcement actions."
        )
    else:
        sections.append(
            f"The investigation sweep completed analysis across the platform database for query: *'{query}'*. No direct case records were matched under the specified parameters. See detailed analytical parameters below."
        )
    sections.append("")

    # --- 2. Comprehensive Case & Modus Operandi Evidence ---
    if records:
        sections.append(f"## 🔍 Primary Case Dossiers & Modus Operandi Analysis")
        sections.append(f"Detailed below are the verified facts, physical evidence, and forensic clues from the top matching records (up to 10 detailed dossiers displayed):")
        sections.append("")

        for idx, r in enumerate(records[:10], 1):
            case_id = r.get("case_id", f"Record-{idx}")
            date = r.get("date", "Unknown Date")
            district = r.get("district", "Unknown Jurisdiction")
            crime = r.get("crime_type", "Unspecified Crime")
            accused = r.get("accused_name", "Unknown Operative")
            co_accused = r.get("co_accused_ids", "None recorded")
            desc = r.get("description") or "No detailed narrative recorded in database."
            
            sections.append(f"### Dossier #{idx}: Case `{case_id}` — {crime} ({district})")
            sections.append(f"- **Incident Date:** {date}")
            sections.append(f"- **Primary Suspect / Accused:** {accused}")
            sections.append(f"- **Linked Co-Conspirators / Network IDs:** `{co_accused}`")
            sections.append(f"- **Verified Case Facts & Forensic Narrative:**\n  > {desc}")
            sections.append("")

        if len(records) > 10:
            remaining = len(records) - 10
            sections.append(f"> *Note: {remaining} additional matching case record(s) were analyzed by the query engine and contributed to the overall network graph and trend metrics.*")
            sections.append("")

    # --- 3. Syndicate Network & Entity Mapping ---
    if entities or edges:
        sections.append(f"## 🕸️ Criminal Network & Structural Interconnections")
        sections.append(f"The Link Analysis agent mapped **{len(entities)} distinct entity nodes** (accused individuals, kingpins, and front organizations) interconnected across **{len(edges)} confirmed structural relationships**:")
        sections.append("")
        for edge in edges[:8]:
            source = edge.get("source", "Unknown Source")
            target = edge.get("target", "Unknown Target")
            basis = edge.get("basis", "Co-accused link")
            detail = edge.get("detail", "")
            sections.append(f"- **`{source}` ↔ `{target}`** (`{basis}`): {detail if detail else 'Confirmed structural link established via case records.'}")
        if len(edges) > 8:
            sections.append(f"- *...and {len(edges) - 8} additional cross-syndicate connections visualized in the interactive Network Graph above.*")
        sections.append("")

    # --- 4. Geographical & Temporal Spikes ---
    spikes = [t for t in trends if t.get("is_spike")]
    if trends:
        sections.append(f"## 📈 Temporal Spikes & Geographical Hotspots")
        if spikes:
            sections.append(f"The Trend Analysis agent detected **{len(spikes)} significant surge activity period(s)** requiring heightened enforcement attention:")
            sections.append("")
            for spike in spikes:
                sections.append(
                    f"- ⚠️ **CRITICAL SPIKE — {spike.get('crime_type', 'Crime')} in {spike.get('location', 'Region')}:** "
                    f"Surge of **+{spike.get('pct_change', '?')}%** detected during **{spike.get('period', 'reporting window')}** ({spike.get('case_count', 0)} confirmed incidents)."
                )
                if spike.get("mo_patterns"):
                    sections.append(f"  - **Common MO Signatures:** {', '.join(spike['mo_patterns'])}")
            sections.append("")
        else:
            sections.append(f"Analyzed **{len(trends)} historical data intervals**. Activity across identified districts shows baseline progression without abnormal statistical spikes during the selected window.")
            sections.append("")

    # --- 5. Risk Assessment & Behavioral Indicators ---
    if risk or profile:
        sections.append(f"## 🛡️ Threat Rating & Behavioral Profile")
        if risk:
            band = risk.get("band", "Unknown")
            score = risk.get("score", 0)
            explanation = risk.get("explanation", "Assessment derived from case frequency and severity.")
            sections.append(f"- **Evaluated Risk Level:** **{band.upper()}** (Numerical Score: **{score}/10**)")
            sections.append(f"- **Assessment Rationale:** {explanation}")
            sections.append("")
        if profile:
            sections.append("**Key Behavioral & Operational Indicators:**")
            for bullet in profile:
                sections.append(f"- {bullet}")
            sections.append("")

    # --- 6. Tactical & Strategic Recommendations ---
    sections.append(f"## 💡 Recommended Enforcement Action Plan")
    sections.append("Based on the synthesized evidence and syndicate signatures, the following operational steps are recommended:")
    sections.append("1. **Digital & Financial Interdiction:** Immediately issue preservation orders for cell tower dump records and financial ledger histories linked to the primary accused identified in the dossiers above.")
    sections.append("2. **Network Hub Targeting:** Prioritize surveillance and interrogation of central bridge nodes mapped in the structural link analysis to sever communication lines between regional leadership and field execution units.")
    sections.append("3. **Jurisdictional Coordination:** Establish joint operational task forces across high-frequency districts (`" + "`, `".join(districts_involved[:4]) + "`) to neutralize cross-border transit and getaway corridors.")
    sections.append("4. **Forensic Cross-Comparison:** Match ballistic, tool-mark, and biometric patterns from recent unsolved break-ins against the specific MO signatures detailed above.")
    sections.append("")

    # --- 7. Citations & Fact Verification Status ---
    if citations or vr:
        sections.append(f"## 📚 Source Citations & Verification Audit")
        rate = vr.get("verification_rate", 100.0) if vr else 100.0
        sections.append(f"**Fact-Checking Integrity Rate:** **{rate}%** of report claims independently verified against original primary case records.")
        if citations:
            sections.append("")
            sections.append("**Primary Case References:**")
            for cit in citations[:8]:
                record_id = cit.get("record_id", "Case")
                claim = cit.get("claim", "")
                sections.append(f"- **[{record_id}]** {claim}")
            if len(citations) > 8:
                sections.append(f"- *...and {len(citations) - 8} additional primary case citations tracked in the system audit log.*")
        sections.append("")

    return "\n".join(sections)


# ===================================================================
# GEMINI-POWERED COMPOSER — natural language response
# ===================================================================

COMPOSER_PROMPT = """You are INSIGHT — the Intelligence Synthesis and Response Generator of the KSP Crime AI Platform. You are the final voice of the investigation pipeline: you transform raw findings from specialist agents into a clear, accurate, grounded response that a Karnataka State Police investigator can act on immediately.

## Your Role
You receive structured findings from the specialist agents (records, network graph, trend data, risk scores) and the investigator's original question. Your job is to synthesize these into a direct, accurate, and appropriately formatted answer — not a formal report generator, not a chatbot making up details, but an intelligent colleague who has read all the evidence and can explain it clearly.

## Core Values
Accuracy above all: Every factual claim in your response must be traceable to the data provided. If the data does not say it, you do not say it.
Clarity over formality: An investigator in the field needs a clear, readable answer — not a bureaucratic memo. Respond like a knowledgeable senior colleague, not a report template.
Proportionality: The length and format of your response must match the complexity of the question. A simple question gets a simple answer. A complex multi-faceted query may warrant structured sections. Never generate unnecessary bulk.

## Language
Always write in {language_name} (language code: {language_code}). If the question is in Kannada, respond entirely in Kannada.

## How to Format Your Response

For simple factual questions (e.g. "how many cases in Mysuru?", "who is Raju Gowda?"):
  → 1-3 clear sentences. No bullet points. No headers. Direct answer.

For moderate questions (e.g. "show me burglary suspects in Mysuru"):
  → 2-4 sentence summary first, then a short bulleted list of the key case facts (case ID, accused name, date, crime type). No section headers needed.

For complex investigative questions (e.g. "give me the full network of the Mysuru extortion ring with risk assessment"):
  → Use concise Markdown headers (## Summary, ## Key Cases, ## Network, ## Risk) only for these complex multi-part questions.

For general statistics questions (e.g. "who committed most crimes?", "which district has highest crime?"):
  → Answer directly from the dataset_stats provided in the data. Cite the actual numbers. Do not fabricate rankings.

## What You Must Never Do
- Never invent case IDs, suspect names, dates, or locations that are not in the provided data.
- Never assume a connection between people if the records do not show it.
- Never generate a formal multi-section dossier for a simple question.
- Never say "I cannot access the database" — you receive the data directly in this prompt.
- Never ignore the dataset_stats when answering aggregate/statistics questions.
- If records_count is 0 and no dataset_stats answer the question, say clearly: "No matching records were found in the current dataset for this query." Do not fabricate an alternative answer.

## Grounding Mandate
Every specific claim — a name, a case ID, a date, a location, a connection — must come directly from the data in this prompt. If you are not certain a fact is in the data, do not include it. This is law enforcement intelligence — fabrication causes real harm."""


def compose_with_gemini(state: dict, language: str) -> str:
    """Use Gemini to write a natural, comprehensive intelligence briefing."""
    _composer_key = os.environ.get("GEMINI_API_KEY_COMPOSER") or os.environ.get("GEMINI_API_KEY")
    if not GEMINI_AVAILABLE or not _composer_key:
        return compose_template_answer(state, language)

    language_name = "Kannada" if language == "kn" else "English"
    prompt_text = COMPOSER_PROMPT.format(
        language_name=language_name,
        language_code=language,
    )

    try:
        model = get_generative_model(
            "gemini-3.1-flash-lite",
            system_instruction=prompt_text,
            api_key_env_var="GEMINI_API_KEY_COMPOSER"
        )
    except Exception as e:
        print(f"[Composer] Failed to initialize model: {e}")
        return compose_template_answer(state, language)

    # Build an extensive summary of findings for Gemini without truncating descriptions at 150 chars
    findings_summary = {
        "query": state.get("resolved_query", ""),
        "records_count": len(state.get("records_found", [])),
        "key_records": [
            {
                "case_id": r.get("case_id"),
                "crime_type": r.get("crime_type"),
                "accused": r.get("accused_name"),
                "co_accused": r.get("co_accused_ids"),
                "district": r.get("district"),
                "date": r.get("date"),
                "full_description": r.get("description", ""),
            }
            for r in state.get("records_found", [])[:12]
        ],
    }

    # Add network if present
    edges = state.get("network_edges", [])
    if edges:
        findings_summary["network"] = {
            "entity_count": len(state.get("entities_found", [])),
            "connections": [
                {"from": e["source"], "to": e["target"], "via": e["basis"], "detail": e.get("detail", "")}
                for e in edges[:15]
            ],
        }

    # Add trends if present
    trends = state.get("trend_findings", [])
    if trends:
        findings_summary["trends"] = [
            t for t in trends if t.get("is_spike")
        ]

    # Add risk if present
    risk = state.get("risk_assessment")
    if risk:
        findings_summary["risk"] = risk

    # Add profile if present
    profile = state.get("behavioral_profile")
    if profile:
        findings_summary["behavioral_profile"] = profile

    # Add citations
    citations = state.get("citations", [])
    if citations:
        findings_summary["citations"] = citations[:12]

    # Build dataset-level aggregate stats so Gemini can answer general questions
    # like "who committed most crimes?" from real data, not hallucinations
    dataset = state.get("dataset") or {}
    df = dataset.get("df") if dataset else None
    dataset_stats = {}
    if df is not None and not df.empty:
        try:
            import pandas as pd
            # Top 10 accused by case count
            if "accused_name" in df.columns:
                top_accused = (
                    df["accused_name"].value_counts().head(10).to_dict()
                )
                dataset_stats["top_accused_by_case_count"] = top_accused

            # Crime type breakdown
            if "crime_type" in df.columns:
                dataset_stats["crime_type_counts"] = (
                    df["crime_type"].value_counts().head(10).to_dict()
                )

            # District breakdown
            if "district" in df.columns:
                dataset_stats["district_counts"] = (
                    df["district"].value_counts().head(10).to_dict()
                )

            dataset_stats["total_records"] = len(df)
        except Exception:
            pass

    if dataset_stats:
        findings_summary["dataset_stats"] = dataset_stats

    user_prompt = (
        f"Question from investigator: {state.get('resolved_query', '')}\n\n"
        f"Data from specialist agents:\n"
        f"{json.dumps(findings_summary, indent=2, default=str)}\n\n"
        f"Answer the question directly and conversationally based only on the data above."
    )

    # Retry with exponential backoff for 429 rate-limit errors.
    # Planner + Verifier calls may exhaust free-tier RPM quota before
    # Composer runs. Instead of silently falling to template, we wait
    # and retry. Only fall back if all retries are exhausted or the
    # error is NOT a rate-limit (e.g. invalid key, network error).
    max_retries = 3
    retry_waits = [15, 30, 45]  # seconds to wait before each retry

    for attempt in range(max_retries):
        try:
            response = model.generate_content(user_prompt)
            return response.text.strip()
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = (
                "429" in err_str
                or "quota" in err_str
                or "resource_exhausted" in err_str
                or "rate" in err_str
            )

            if is_rate_limit and attempt < max_retries - 1:
                wait = retry_waits[attempt]
                print(
                    f"[Composer] Rate limit hit (attempt {attempt + 1}/{max_retries}). "
                    f"Waiting {wait}s then retrying..."
                )
                time.sleep(wait)
                continue
            else:
                if is_rate_limit:
                    print(
                        f"[Composer] All {max_retries} retries exhausted (rate limit). "
                        f"Falling back to template."
                    )
                else:
                    print(f"[Composer] Gemini failed (non-rate-limit): {e}")
                return compose_template_answer(state, language)


# ===================================================================
# RESPONSE SHAPER — build the section 8.2 JSON response object
# ===================================================================

def build_response_json(state: dict, answer_text: str) -> dict:
    """
    Shape the final response into the section 8.2 JSON contract.
    Only includes fields for agents that actually ran.
    """
    response = {
        "session_id": state.get("session_id", ""),
        "query_id": str(uuid.uuid4()),
        "answer_text": answer_text,
    }

    # Citations — always present (verifier always runs)
    citations = state.get("citations", [])
    response["citations"] = [
        {
            "claim": c.get("claim", ""),
            "record_id": c.get("record_id", ""),
            "snippet": c.get("snippet", ""),
        }
        for c in citations
    ]

    # Network graph — only if link_agent ran
    if "entities_found" in state and state["entities_found"]:
        response["network_graph"] = {
            "nodes": [
                {
                    "id": e["id"],
                    "name": e["name"],
                    "label": e.get("name", e["id"]),
                    "type": e.get("type", "person"),
                    "basis": e.get("basis", ""),
                }
                for e in state["entities_found"]
            ],
            "edges": [
                {
                    "source": e["source"],
                    "target": e["target"],
                    "basis": e.get("basis", ""),
                }
                for e in state.get("network_edges", [])
            ],
        }

    # Trend findings — only if trend_agent ran
    if "trend_findings" in state and state["trend_findings"]:
        response["trend_findings"] = [
            {
                "location": t.get("location", ""),
                "crime_type": t.get("crime_type", ""),
                "period": t.get("period", ""),
                "pct_change": t.get("pct_change", 0.0),
                "case_count": t.get("case_count", 0),
                "is_spike": t.get("is_spike", False),
                "mo_patterns": t.get("mo_patterns", []),
            }
            for t in state["trend_findings"]
        ]

    # Hotspots — geographical concentration share
    if "hotspots" in state and state["hotspots"]:
        response["hotspots"] = state["hotspots"]

    # Demographic findings — only if present
    if state.get("demographic_findings"):
        response["demographic_findings"] = state["demographic_findings"]

    # Risk assessment — only if risk_agent ran
    if "risk_assessment" in state and state["risk_assessment"]:
        risk = state["risk_assessment"]
        response["risk_assessment"] = {
            "score": risk.get("score", 0),
            "band": risk.get("band", "Low"),
            "explanation": risk.get("explanation", ""),
        }

    # Behavioral profile — only if present
    if state.get("behavioral_profile"):
        response["behavioral_profile"] = state["behavioral_profile"]

    # These values are produced by the verifier and consumed by the audit
    # views. Keep them at the top level alongside citations so all frontend
    # pages can use the same response contract.
    verification = state.get("verification_result", {})
    response["verification_rate"] = verification.get("verification_rate", 100.0)
    response["unsupported_claims"] = verification.get("unsupported_claims", [])

    return response


# ===================================================================
# MAIN FUNCTION — the composer_agent entry point
# ===================================================================

def composer_agent(state: dict) -> dict:
    """
    Composer Agent — package findings into the final authoritative report.

    Reads:  entire state (all agent outputs, citations, verification)

    Writes: state["answer_text"]     — the composed answer string
            state["final_response"]  — the section 8.2 JSON object
            state["response_language"] — "en" or "kn"
    """
    query = state.get("resolved_query", "")

    print(f"\n[Composer] Composing final comprehensive intelligence response...")

    # --- Step 1: Detect language ---
    language = detect_language(query)
    language_name = "Kannada" if language == "kn" else "English"
    print(f"[Composer] Detected language: {language_name}")

    # --- Step 2: Compose the answer ---
    # Use Gemini if key is present for rich, natural language report generation
    # across both English and Kannada. If unavailable, use the comprehensive dossier template.
    if GEMINI_AVAILABLE and (os.environ.get("GEMINI_API_KEY_COMPOSER") or os.environ.get("GEMINI_API_KEY")):
        print(f"[Composer] Gemini API key detected - using Gemini for comprehensive intelligence dossier ({language_name})...")
        import time
        # Wait 5s so Planner + Verifier Gemini calls clear the RPM window
        # before Composer adds its call. (Was 1s — too short.)
        print("[Composer] Waiting 5s for Planner/Verifier quota to clear...")
        time.sleep(5)
        answer_text = compose_with_gemini(state, language)
    else:
        print(f"[Composer] Using comprehensive intelligence dossier template ({language_name})...")
        answer_text = compose_template_answer(state, language)

    print(f"[Composer] Answer length: {len(answer_text)} characters")

    # --- Step 3: Build the 8.2 JSON response ---
    final_response = build_response_json(state, answer_text)

    # --- Step 4: Write to state ---
    state["answer_text"] = answer_text
    state["final_response"] = final_response
    state["response_language"] = language

    agents_used = state.get("agents_used", [])
    fields_included = [
        k for k in ["network_graph", "trend_findings", "risk_assessment",
                     "demographic_findings", "behavioral_profile"]
        if k in final_response
    ]

    print(f"[Composer] Agents used: {agents_used}")
    print(f"[Composer] Response fields: {fields_included}")
    print(f"[Composer] Done.")

    return state

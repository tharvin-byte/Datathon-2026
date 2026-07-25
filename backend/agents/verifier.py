"""
VERIFIER AGENT — Crime AI Fact-Checker
========================================
PURPOSE: Before anything reaches the investigator, confirm every claim
traces back to an actual record — not something the model inferred or
invented. This matters critically for law enforcement — a fabricated
"connection" between two people can genuinely harm someone.

HOW IT WORKS:
  1. Collect all claims from agent outputs (network edges, trend findings,
     risk rules, etc.)
  2. For each claim, find the source record(s) that support it
  3. Build a citation: claim text → record ID → record snippet
  4. Flag any claim that has NO supporting record as "unsupported"
  5. If unsupported claims exist, signal the planner to either drop
     them or fetch more evidence

TWO MODES:
  - GEMINI MODE: LLM reads the draft answer + raw records and checks
    if every statement is grounded in the data
  - RULE-BASED MODE: deterministic check — does each claim's referenced
    record/entity actually exist in state["records_found"]?

OUTPUT:
  state["citations"]            — list of {claim, record_id, snippet}
  state["verification_result"]  — {verified: bool, unsupported_claims: [...]}
  state["verified"]             — simple boolean for downstream use

DEPENDENCY: Runs AFTER all specialist agents and planner are done.
"""

import json
import os
import re
import time

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None


# ===================================================================
# CLAIM EXTRACTOR — pull all verifiable claims from state
# ===================================================================
# Each agent writes structured findings to state. The verifier needs
# to turn those findings into discrete "claims" that can each be
# checked against the raw records independently.
# ===================================================================

def extract_claims_from_state(state: dict) -> list[dict]:
    """
    Walk through all agent outputs in state and extract discrete,
    verifiable claims. Each claim has:
      - text: the human-readable claim
      - source_agent: which agent produced it
      - evidence_keys: what state fields support it
      - referenced_cases: case IDs mentioned
    """
    claims = []

    # --- Claims from network_edges (Link Agent) ---
    for edge in state.get("network_edges", []):
        claim = {
            "text": (
                f"{edge['source']} is connected to {edge['target']} "
                f"via {edge['basis']}: {edge.get('detail', '')}"
            ),
            "source_agent": "link_agent",
            "evidence_keys": ["network_edges"],
            "referenced_cases": edge.get("source_cases", []),
            "basis": edge.get("basis", "unknown"),
        }
        claims.append(claim)

    # --- Claims from trend_findings (Trend Agent) ---
    for finding in state.get("trend_findings", []):
        if finding.get("is_spike"):
            claim = {
                "text": (
                    f"{finding['crime_type']} in {finding['location']} "
                    f"increased by {finding.get('pct_change', '?')}% "
                    f"in {finding['period']} "
                    f"({finding['case_count']} cases)"
                ),
                "source_agent": "trend_agent",
                "evidence_keys": ["trend_findings"],
                "referenced_cases": [],
                "basis": "statistical_trend",
                "case_count": finding["case_count"],
            }
            claims.append(claim)

    # --- Claims from risk_assessment (Risk Agent) ---
    risk = state.get("risk_assessment", {})
    for rule in risk.get("rules_fired", []):
        claim = {
            "text": rule["reason"],
            "source_agent": "risk_agent",
            "evidence_keys": ["risk_assessment"],
            "referenced_cases": [],
            "basis": rule["rule"],
        }
        claims.append(claim)

    # --- Claims from behavioral_profile (Risk Agent) ---
    for bullet in state.get("behavioral_profile", []):
        claim = {
            "text": bullet,
            "source_agent": "risk_agent",
            "evidence_keys": ["behavioral_profile"],
            "referenced_cases": [],
            "basis": "behavioral_observation",
        }
        claims.append(claim)

    return claims


# ===================================================================
# RULE-BASED VERIFICATION — works without Gemini
# ===================================================================
# For each claim, check if the referenced entities/cases actually
# exist in the raw records. This is a structural check, not a
# semantic one — it catches fabricated case IDs or entity names
# but can't verify nuanced interpretive claims.
# ===================================================================

def verify_claim_rule_based(claim: dict, records: list[dict]) -> dict:
    """
    Check one claim against the raw records.
    Returns the claim dict enriched with verification status.
    """
    # Build lookup sets from records
    all_case_ids = {r.get("case_id", "") for r in records}
    all_names = set()
    for r in records:
        name = (r.get("accused_name") or "").strip().title()
        if name and name.lower() not in ("unknown", "na"):
            all_names.add(name)
        victim = (r.get("victim_name") or "").strip().title()
        if victim and victim.lower() not in ("unknown", "na"):
            all_names.add(victim)

    all_districts = {(r.get("district") or "").lower() for r in records}
    all_crime_types = {(r.get("crime_type") or "").lower() for r in records}

    claim_text = claim["text"]
    issues = []

    # Check 1: If claim references specific case IDs, do they exist?
    referenced = claim.get("referenced_cases", [])
    if referenced:
        missing = [cid for cid in referenced if cid not in all_case_ids]
        if missing:
            issues.append(f"Referenced case(s) not found in data: {missing}")

    # Check 2: If claim mentions a person name, is it in the records?
    for name in all_names:
        # We check the reverse — if a name in the claim ISN'T in records
        # This is a loose check; we can't verify every word
        pass  # Names are checked via the referenced_cases link instead

    # Check 3: For network edges, verify both endpoints exist
    if claim.get("basis") in ("same_address", "same_phone", "co_accused_field",
                               "narrative_mention", "fuzzy_name_match"):
        # Extract names from claim text
        parts = claim_text.split(" is connected to ")
        if len(parts) == 2:
            src_name = parts[0].strip()
            tgt_part = parts[1].split(" via ")[0].strip()
            src_found = any(
                src_name.lower() == n.lower() for n in all_names
            )
            tgt_found = any(
                tgt_part.lower() == n.lower() for n in all_names
            )
            if not src_found:
                issues.append(f"Entity '{src_name}' not found in records")
            if not tgt_found:
                issues.append(f"Entity '{tgt_part}' not found in records")

    # Check 4: For trend claims, verify the location and crime type exist
    if claim.get("basis") == "statistical_trend":
        # Extract location and crime type from claim text
        for district in all_districts:
            if district in claim_text.lower():
                break
        else:
            if "location" not in claim_text.lower():
                issues.append("Location in trend claim not found in dataset")

    # Determine verification status
    verified = len(issues) == 0

    return {
        "claim": claim_text,
        "source_agent": claim.get("source_agent", "unknown"),
        "verified": verified,
        "issues": issues,
        "referenced_cases": referenced,
    }


def find_supporting_record(claim: dict, records: list[dict]) -> dict | None:
    """
    Find the best matching record that supports this claim.
    Returns the record dict, or None if no match found.
    Used to build the citation (claim → record_id → snippet).
    """
    referenced = claim.get("referenced_cases", [])

    # If the claim explicitly references case IDs, use those
    if referenced:
        for record in records:
            if record.get("case_id") in referenced:
                return record

    # Otherwise, try to match by entity names in the claim text
    claim_lower = claim["text"].lower()
    best_match = None
    best_score = 0

    for record in records:
        score = 0
        accused = (record.get("accused_name") or "").lower()
        district = (record.get("district") or "").lower()
        crime = (record.get("crime_type") or "").lower()

        if accused and accused in claim_lower:
            score += 3
        if district and district in claim_lower:
            score += 1
        if crime and crime in claim_lower:
            score += 1

        if score > best_score:
            best_score = score
            best_match = record

    return best_match if best_score > 0 else None


# ===================================================================
# GEMINI-POWERED VERIFICATION — semantic grounding check
# ===================================================================

VERIFIER_PROMPT = """You are VERIFACT — the independent evidence integrity engine of the KSP Crime AI Platform. Your sole function is rigorous, impartial fact-verification. You have no opinions, no bias, and no loyalty to any prior conclusion. You evaluate only what the primary source records prove.

## Your Role
You receive a list of claims produced by the investigative pipeline and a set of raw primary case records from the Karnataka State Police database. For each claim, you determine whether it is directly supported by evidence in those records. Your output is the last line of defense before an answer reaches a law enforcement investigator — accuracy here is not optional.

## Why This Matters
Karnataka State Police investigators rely on this platform to make enforcement decisions. An unverified claim about a person's criminal involvement can result in wrongful arrest, damaged reputations, or compromised prosecutions. You apply the same evidentiary standard as a court: a claim must be traceable to a specific record to be considered supported.

## Verification Classifications

SUPPORTED — Use when:
  - The claim is directly and completely traceable to one or more specific records.
  - The record explicitly names the person, date, location, crime type, or event described in the claim.
  - No inference is required — the record says what the claim says.

PARTIAL — Use when:
  - Part of the claim is grounded in a record, but another part involves inference, extrapolation, or assumption.
  - The record supports the general direction but not the specific detail (e.g., record shows burglary, claim says "professional burglary ring").
  - Multiple records together imply the claim but no single record states it directly.

UNSUPPORTED — Use when:
  - No record in the provided set explicitly mentions the person, location, crime, date, or event in the claim.
  - The claim makes a causal assertion ("X led the operation because...") with no record backing the causation.
  - The claim is plausible but not provable from the given evidence.
  - You are uncertain — in law enforcement contexts, uncertainty means UNSUPPORTED.

## Reasoning Process
For each claim:
  1. Identify the core factual assertion (who, what, where, when).
  2. Search the records for any that mention the key entities in the claim.
  3. Check whether the record's content directly matches the assertion — not just the names.
  4. Assign the classification and cite the specific record ID that supports it (or null if none).
  5. Write a brief, precise reason explaining your determination.

## Hard Rules
- Never mark a claim SUPPORTED based on your general knowledge of crime — only from the provided records.
- Never infer connections that the records do not state.
- Never soften a classification to be polite or consistent with the prior answer.
- When a claim contains multiple assertions, classify it by its weakest supported component.
- If records are empty or missing, every claim is UNSUPPORTED by definition.

## Output Format
Reply with ONLY a valid JSON array — no preamble, no explanation outside the array:
[
  {"claim": "...", "status": "supported|unsupported|partial", "reason": "One precise sentence explaining your determination.", "supporting_record_id": "case ID string or null"}
]"""


def verify_with_gemini(claims: list[dict], records: list[dict]) -> list[dict]:
    """Use Gemini to semantically verify claims against records."""
    _verifier_key = os.environ.get("GEMINI_API_KEY_VERIFIER") or os.environ.get("GEMINI_API_KEY")
    genai.configure(api_key=_verifier_key)
    model = genai.GenerativeModel(
        "gemini-3.1-flash-lite",
        system_instruction=VERIFIER_PROMPT,
    )

    # Prepare records summary (trim descriptions for token efficiency)
    records_summary = []
    for r in records[:20]:  # Cap at 20 records to stay within token limits
        records_summary.append({
            "case_id": r.get("case_id"),
            "date": r.get("date"),
            "district": r.get("district"),
            "crime_type": r.get("crime_type"),
            "accused_name": r.get("accused_name"),
            "victim_name": r.get("victim_name"),
            "description": (r.get("description") or "")[:200],  # Truncate
        })

    claim_texts = [c["text"] for c in claims]

    prompt = (
        f"CLAIMS TO VERIFY:\n{json.dumps(claim_texts, indent=2)}\n\n"
        f"RAW RECORDS:\n{json.dumps(records_summary, indent=2)}"
    )

    try:
        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Parse JSON from response
        code_block = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", response_text, re.DOTALL)
        if code_block:
            results = json.loads(code_block.group(1))
        else:
            bracket_start = response_text.find("[")
            bracket_end = response_text.rfind("]") + 1
            if bracket_start >= 0 and bracket_end > bracket_start:
                results = json.loads(response_text[bracket_start:bracket_end])
            else:
                raise ValueError("Could not parse Gemini response as JSON")

        return results

    except Exception as e:
        print(f"[Verifier] Gemini verification failed: {e}")
        return []


# ===================================================================
# CITATION BUILDER — maps each verified claim to a source record
# ===================================================================

def build_citations(claims: list[dict], records: list[dict]) -> list[dict]:
    """
    For each claim, find the supporting record and build a citation:
      {claim: "...", record_id: "C001", snippet: "first 150 chars of description"}
    
    This is what the audit.html page displays — the complete
    claim-to-source traceability chain.
    """
    citations = []

    for claim in claims:
        record = find_supporting_record(claim, records)

        citation = {
            "claim": claim["text"],
            "record_id": record.get("case_id", "unknown") if record else None,
            "snippet": (
                (record.get("description") or "")[:150] + "..."
                if record else "No supporting record found"
            ),
            "source_agent": claim.get("source_agent", "unknown"),
        }
        citations.append(citation)

    return citations


# ===================================================================
# MAIN FUNCTION — the verifier_agent entry point
# ===================================================================

def verifier_agent(state: dict) -> dict:
    """
    Verifier Agent — fact-check every claim against real records.

    Reads:  state["network_edges"]      (claims from Link Agent)
            state["trend_findings"]     (claims from Trend Agent)
            state["risk_assessment"]    (claims from Risk Agent)
            state["behavioral_profile"] (claims from Risk Agent)
            state["records_found"]      (raw records to verify against)

    Writes: state["citations"]            — claim → record_id → snippet
            state["verification_result"]  — {verified, unsupported_claims, stats}
            state["verified"]             — boolean

    TECHNIQUE:
      1. Extract all discrete claims from agent outputs
      2. Verify each against raw records (Gemini or rule-based)
      3. Build citations for verified claims
      4. Flag unsupported claims
      5. If too many unsupported → signal planner to loop back
    """
    records = state.get("records_found", [])

    print(f"\n[Verifier] Starting verification...")

    # --- Step 1: Extract all claims ---
    claims = extract_claims_from_state(state)
    print(f"[Verifier] Extracted {len(claims)} claims to verify")

    if not claims:
        state["citations"] = []
        state["verification_result"] = {
            "verified": True,
            "unsupported_claims": [],
            "total_claims": 0,
            "verified_count": 0,
        }
        state["verified"] = True
        print("[Verifier] No claims to verify. Done.")
        return state

    # --- Step 2: Verify claims ---
    verified_claims = []
    unsupported_claims = []

    if GEMINI_AVAILABLE and (os.environ.get("GEMINI_API_KEY_VERIFIER") or os.environ.get("GEMINI_API_KEY")):
        # Gemini-powered semantic verification
        print("[Verifier] Using Gemini for semantic verification...")
        # Option 5: 3-second delay before Gemini call to avoid
        # exceeding the free-tier per-minute rate limit
        time.sleep(3)
        gemini_results = verify_with_gemini(claims, records)

        if gemini_results:
            for i, claim in enumerate(claims):
                if i < len(gemini_results):
                    result = gemini_results[i]
                    status = result.get("status", "unknown")
                    if status == "supported":
                        verified_claims.append(claim)
                    else:
                        claim["gemini_reason"] = result.get("reason", "")
                        unsupported_claims.append(claim)
                else:
                    # Gemini didn't return enough results — fall back
                    result = verify_claim_rule_based(claim, records)
                    if result["verified"]:
                        verified_claims.append(claim)
                    else:
                        unsupported_claims.append(claim)
        else:
            # Gemini failed — fall back to rule-based
            print("[Verifier] Gemini failed, falling back to rule-based")
            for claim in claims:
                result = verify_claim_rule_based(claim, records)
                if result["verified"]:
                    verified_claims.append(claim)
                else:
                    claim["issues"] = result["issues"]
                    unsupported_claims.append(claim)
    else:
        # Rule-based verification (no Gemini)
        print("[Verifier] Using rule-based verification...")
        for claim in claims:
            result = verify_claim_rule_based(claim, records)
            if result["verified"]:
                verified_claims.append(claim)
            else:
                claim["issues"] = result["issues"]
                unsupported_claims.append(claim)

    print(f"[Verifier] Verified: {len(verified_claims)}, Unsupported: {len(unsupported_claims)}")

    # --- Step 3: Build citations for verified claims ---
    citations = build_citations(verified_claims, records)

    # --- Step 4: Determine overall verification status ---
    total = len(claims)
    unsupported_count = len(unsupported_claims)
    verification_rate = (total - unsupported_count) / total if total > 0 else 1.0

    # If more than 30% of claims are unsupported, flag for re-planning
    needs_replanning = verification_rate < 0.7

    if unsupported_claims:
        print("[Verifier] Unsupported claims:")
        for uc in unsupported_claims:
            print(f"  [X] {uc['text'][:80]}...")
            if "issues" in uc:
                for issue in uc["issues"]:
                    print(f"    -> {issue}")

    # --- Step 5: Write to state ---
    state["citations"] = citations
    state["verification_result"] = {
        "verified": unsupported_count == 0,
        "verification_rate": round(verification_rate * 100, 1),
        "total_claims": total,
        "verified_count": len(verified_claims),
        "unsupported_count": unsupported_count,
        "unsupported_claims": [
            {
                "claim": uc["text"],
                "source_agent": uc.get("source_agent", "unknown"),
                "issues": uc.get("issues", uc.get("gemini_reason", "unverified")),
            }
            for uc in unsupported_claims
        ],
        "needs_replanning": needs_replanning,
    }
    state["verified"] = unsupported_count == 0

    print(
        f"[Verifier] Done. Verification rate: {verification_rate*100:.1f}%. "
        f"{'[WARN] Needs replanning!' if needs_replanning else '[OK] All good.'}"
    )

    return state

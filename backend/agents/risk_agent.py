"""
RISK AGENT (Agent 4) — Crime AI
=================================
PURPOSE: Combine Link Agent and Trend Agent outputs into a single,
explainable risk assessment with a numeric score and band.

THIS IS RULES-BASED, NOT ML:
  - A fixed scoring rubric with clearly defined rules
  - Each rule that fires adds points and logs WHY it fired
  - The explanation is template-filled, not LLM-generated
  - An investigator (or judge) can see exactly which rules produced
    the score — full traceability, no black box

SCORING RUBRIC:
  +2  Trend spike (>=25% increase) in the relevant zone
  +2  A linked entity has a prior record of the same crime type
  +1  Per additional connected entity with any prior record
  +1  Hub node (>=3 connections) exists in the network
  +1  Repeat offender detected (same person in multiple cases)
  +1  Cross-district links detected in the network
  +1  Active MO pattern identified in spike descriptions

RISK BANDS:
  0-2  = Low    (green)
  3-5  = Medium (amber)
  6+   = High   (red)

INPUT:  state["network_edges"], state["entities_found"],
        state["trend_findings"], state["network_analysis"],
        state["records_found"], state["mo_patterns"]
OUTPUT: state["risk_assessment"]    — score, band, explanation
        state["behavioral_profile"] — bullet points describing patterns

DEPENDENCY: Runs LAST — needs both Link Agent and Trend Agent to finish first.
"""


# ===================================================================
# SCORING RUBRIC — each function checks one rule, returns points + reason
# ===================================================================
# Every rule is a separate function that:
#   1. Checks a specific condition against state data
#   2. Returns (points, reason_string) if the rule fires
#   3. Returns (0, None) if it doesn't
#
# This makes the rubric easy to extend — add a new rule = add a new
# function and register it in SCORING_RULES.
# ===================================================================

def rule_trend_spike(state: dict) -> tuple[int, str | None]:
    """
    +2 points if there's a trend spike (>=25% increase) in any zone.
    WHY: A rising trend means the problem is getting worse, not stable.
    """
    trend_findings = state.get("trend_findings", [])
    spikes = [f for f in trend_findings if f.get("is_spike")]

    if not spikes:
        return 0, None

    # Take the worst spike
    worst = max(spikes, key=lambda f: f.get("pct_change", 0) or 0)
    pct = worst.get("pct_change", 0)
    location = worst.get("location", "unknown")
    crime = worst.get("crime_type", "unknown")

    return 2, (
        f"{location} shows a {pct}% increase in {crime} — "
        f"trend is rising, not a one-off"
    )


def rule_prior_record_same_type(state: dict) -> tuple[int, str | None]:
    """
    +2 points if a linked entity has a prior record of the SAME crime type.
    WHY: A repeat offender for the same crime type is a stronger signal
    than someone with unrelated priors.
    """
    entities = state.get("entities_found", [])
    records = state.get("records_found", [])

    if not entities or not records:
        return 0, None

    # Build a map: person → list of crime types they're involved in
    person_crimes = {}
    for record in records:
        name = (record.get("accused_name") or "").strip().title()
        crime = record.get("crime_type", "")
        if name and name.lower() not in ("unknown", "na"):
            person_crimes.setdefault(name, []).append(crime)

    # Check if anyone has multiple cases of the same crime type
    repeat_same_type = []
    for person, crimes in person_crimes.items():
        if len(crimes) >= 2:
            # Check for same-type repeats
            from collections import Counter
            crime_counts = Counter(crimes)
            for crime, count in crime_counts.items():
                if count >= 2:
                    repeat_same_type.append((person, crime, count))

    if not repeat_same_type:
        return 0, None

    worst = max(repeat_same_type, key=lambda x: x[2])
    return 2, (
        f"{worst[0]} has {worst[2]} prior record(s) of {worst[1]} — "
        f"repeat offender for the same crime type"
    )


def rule_connected_entities_with_priors(state: dict) -> tuple[int, str | None]:
    """
    +1 point per additional connected entity with any prior record (max +3).
    WHY: More people in the network with priors = more organized activity.
    """
    entities = state.get("entities_found", [])

    # Count entities that appear in more than one case
    multi_case = [
        e for e in entities
        if len(e.get("cases", [])) > 1 and e.get("type") == "accused"
    ]

    if not multi_case:
        return 0, None

    points = min(len(multi_case), 3)  # Cap at 3 points
    names = [e["name"] for e in multi_case[:3]]

    return points, (
        f"{len(multi_case)} connected entities have prior records: "
        f"{', '.join(names)}"
    )


def rule_hub_node(state: dict) -> tuple[int, str | None]:
    """
    +1 point if a hub node (>=3 connections) exists in the network.
    WHY: A highly connected person is likely a key player / organizer.
    """
    analysis = state.get("network_analysis", {})
    hubs = analysis.get("hub_nodes", [])

    significant_hubs = [h for h in hubs if h.get("connections", 0) >= 3]

    if not significant_hubs:
        return 0, None

    top = significant_hubs[0]
    return 1, (
        f"{top['name']} is a network hub with {top['connections']} connections — "
        f"potential key player or organizer"
    )


def rule_repeat_offender(state: dict) -> tuple[int, str | None]:
    """
    +1 point if the same accused appears in multiple cases.
    WHY: Repeat involvement suggests ongoing criminal activity.
    """
    records = state.get("records_found", [])

    name_counts = {}
    for record in records:
        name = (record.get("accused_name") or "").strip().title()
        if name and name.lower() not in ("unknown", "na"):
            name_counts[name] = name_counts.get(name, 0) + 1

    repeaters = {n: c for n, c in name_counts.items() if c >= 2}

    if not repeaters:
        return 0, None

    top_name = max(repeaters, key=repeaters.get)
    return 1, (
        f"{top_name} appears in {repeaters[top_name]} cases — "
        f"repeat offender detected"
    )


def rule_cross_district(state: dict) -> tuple[int, str | None]:
    """
    +1 point if the network has links across different districts.
    WHY: Cross-district activity suggests organized crime or
    a suspect operating across jurisdictions to avoid detection.
    """
    edges = state.get("network_edges", [])
    records = state.get("records_found", [])

    if not edges or not records:
        return 0, None

    # Build person → districts mapping
    person_districts = {}
    for record in records:
        name = (record.get("accused_name") or "").strip().title()
        district = record.get("district", "")
        if name and district:
            person_districts.setdefault(name, set()).add(district)

    # Check if any connected pair spans different districts
    for edge in edges:
        src_districts = person_districts.get(edge["source"], set())
        tgt_districts = person_districts.get(edge["target"], set())
        combined = src_districts | tgt_districts
        if len(combined) >= 2:
            return 1, (
                f"Network spans multiple districts ({', '.join(combined)}) — "
                f"possible cross-jurisdictional activity"
            )

    return 0, None


def rule_active_mo_pattern(state: dict) -> tuple[int, str | None]:
    """
    +1 point if an active MO pattern was identified in a spike.
    WHY: A consistent MO across multiple cases in a spike suggests
    the same perpetrator or an organized method.
    """
    mo_patterns = state.get("mo_patterns", {})

    if not mo_patterns:
        return 0, None

    # Take the first pattern group
    key = list(mo_patterns.keys())[0]
    patterns = mo_patterns[key]

    if not patterns:
        return 0, None

    return 1, (
        f"Active MO pattern detected in {key.replace('_', ' ')}: "
        f"{patterns[0]}"
    )


# ===================================================================
# ALL RULES — register them here. To add a new rule, write the
# function above and add it to this list. That's it.
# ===================================================================

SCORING_RULES = [
    rule_trend_spike,
    rule_prior_record_same_type,
    rule_connected_entities_with_priors,
    rule_hub_node,
    rule_repeat_offender,
    rule_cross_district,
    rule_active_mo_pattern,
]


# ===================================================================
# BEHAVIORAL PROFILE — generate bullet points from state
# ===================================================================
# These are descriptive observations (not scores), presented as
# bullet points to the investigator. Built from templates, not LLM.
# ===================================================================

def build_behavioral_profile(state: dict) -> list[str]:
    """
    Generate plain-language bullet points describing behavioral patterns.
    Each bullet is template-filled from actual state data.
    """
    bullets = []
    records = state.get("records_found", [])
    entities = state.get("entities_found", [])
    edges = state.get("network_edges", [])
    trends = state.get("trend_findings", [])

    # --- Repeat offender pattern ---
    name_counts = {}
    for r in records:
        name = (r.get("accused_name") or "").strip().title()
        if name and name.lower() not in ("unknown", "na"):
            name_counts[name] = name_counts.get(name, 0) + 1

    for name, count in name_counts.items():
        if count >= 2:
            crimes = [
                r.get("crime_type", "unknown")
                for r in records
                if (r.get("accused_name") or "").strip().title() == name
            ]
            bullets.append(
                f"Repeat offender: {name} appears in {count} cases "
                f"({', '.join(set(crimes))})"
            )

    # --- Network size observation ---
    if entities:
        accused_count = sum(1 for e in entities if e.get("type") == "accused")
        bullets.append(
            f"Criminal network involves {accused_count} accused individuals "
            f"and {len(edges)} connections"
        )

    # --- Geographic spread ---
    districts = set()
    for r in records:
        d = r.get("district", "")
        if d:
            districts.add(d)
    if len(districts) > 1:
        bullets.append(
            f"Activity spans {len(districts)} districts: {', '.join(districts)}"
        )
    elif len(districts) == 1:
        bullets.append(f"Activity concentrated in {list(districts)[0]}")

    # --- Time pattern ---
    dates = []
    for r in records:
        d = r.get("date", "")
        if d:
            dates.append(d)
    if dates:
        dates_sorted = sorted(dates)
        bullets.append(
            f"Timeframe: {dates_sorted[0]} to {dates_sorted[-1]} "
            f"({len(dates)} incidents)"
        )

    # --- Trend observation ---
    spikes = [f for f in trends if f.get("is_spike")]
    if spikes:
        for spike in spikes[:2]:
            bullets.append(
                f"Trending: {spike['crime_type']} in {spike['location']} "
                f"up {spike.get('pct_change', '?')}% — active spike"
            )

    # --- Co-accused network ---
    co_accused_edges = [e for e in edges if e.get("basis") == "co_accused_field"]
    if co_accused_edges:
        bullets.append(
            f"{len(co_accused_edges)} co-accused relationship(s) found — "
            f"suggests organized activity"
        )

    return bullets


# ===================================================================
# MAIN FUNCTION — the risk_agent entry point
# ===================================================================

def risk_agent(state: dict) -> dict:
    """
    Risk Agent — produce an explainable risk assessment.

    Reads:  state["network_edges"]    (from Link Agent)
            state["entities_found"]   (from Link Agent)
            state["network_analysis"] (from Link Agent)
            state["trend_findings"]   (from Trend Agent)
            state["mo_patterns"]      (from Trend Agent)
            state["records_found"]    (from Query Agent)

    Writes: state["risk_assessment"]    — {score, band, explanation, rules_fired}
            state["behavioral_profile"] — list of descriptive bullet strings

    TECHNIQUE: Fixed scoring rubric. Each rule is a separate function
    that checks one condition and returns points + a reason string.
    The explanation is built from concatenating the reasons of all
    rules that fired — fully traceable, no LLM generation.
    """
    print("[RiskAgent] Computing risk assessment...")

    # --- Run every rule in the rubric ---
    total_score = 0
    reasons = []
    rules_fired = []

    for rule_fn in SCORING_RULES:
        points, reason = rule_fn(state)
        if points > 0 and reason:
            total_score += points
            reasons.append(reason)
            rules_fired.append({
                "rule": rule_fn.__name__,
                "points": points,
                "reason": reason,
            })
            print(f"[RiskAgent]   {rule_fn.__name__}: +{points} — {reason}")

    # --- Determine risk band ---
    if total_score <= 2:
        band = "Low"
    elif total_score <= 5:
        band = "Medium"
    else:
        band = "High"

    # --- Build explanation string ---
    if reasons:
        explanation = " | ".join(reasons) + f" — Overall Risk: {band}"
    else:
        explanation = "No significant risk indicators found — Risk: Low"

    # --- Build behavioral profile ---
    profile = build_behavioral_profile(state)

    # --- Write to state ---
    state["risk_assessment"] = {
        "score": total_score,
        "band": band,
        "explanation": explanation,
        "rules_fired": rules_fired,
    }
    state["behavioral_profile"] = profile

    print(f"[RiskAgent] Score: {total_score}, Band: {band}")
    print(f"[RiskAgent] {len(rules_fired)} rules fired, {len(profile)} profile bullets")
    print(f"[RiskAgent] Done.")

    return state

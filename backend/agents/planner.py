"""
PLANNER AGENT — Crime AI Orchestrator
=======================================
PURPOSE: The piece that makes this a GOAL-BASED agent, not a chatbot.

Given the investigator's question, the planner:
  1. Decides which specialist agents are needed
  2. Calls them in the right order (respecting dependencies)
  3. Reads what came back
  4. Asks: "Is this enough to answer the question?"
  5. If not → plans another step (the ReAct loop)
  6. If yes → passes everything to the Verifier

TECHNIQUE: ReAct (Reason-Act-Observe) loop
  - REASON: Gemini analyzes the question + current state
  - ACT:    Gemini picks which agent(s) to call via function-calling
  - OBSERVE: Results come back into state
  - LOOP:   Gemini re-evaluates — enough info, or need another step?

The planner is the ONLY component that uses Gemini for decision-making
(the four specialist agents are all deterministic Python).

CONVERSATION HISTORY:
  Instead of a separate "context normalizer" agent, the last few turns
  of conversation are passed directly into the planner's prompt. This
  lets Gemini resolve pronouns ("show me HIS associates") and follow-up
  references without a separate rewriting step.

DEPENDENCY ENFORCEMENT:
  query_agent must run before link/trend agents.
  risk_agent must run after both link and trend agents.
  The planner respects this even if Gemini tries to skip ahead.
"""

import json
import os
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# Gemini setup — using google-generativeai SDK
# The planner uses Gemini's function-calling feature: we describe each
# specialist agent as a "tool" with a name and description, and Gemini
# decides which to call based on the question.
# ---------------------------------------------------------------------------
try:
    from core.llm_client import get_generative_model
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# Import the four specialist agents
from agents.query_agent import query_agent
from agents.link_agent import link_agent
from agents.trend_agent import trend_agent
from agents.risk_agent import risk_agent


# ===================================================================
# TOOL DEFINITIONS — describe each agent as a callable tool for Gemini
# ===================================================================
# These descriptions tell Gemini WHAT each agent does so it can decide
# WHEN to call it. The planner never lets Gemini run the agents
# directly — Gemini just picks the name, and we execute the actual
# Python function ourselves. This keeps the agents deterministic.
# ===================================================================

AGENT_TOOLS = [
    {
        "name": "query_agent",
        "description": (
            "Fetch matching crime records from the dataset. Use this FIRST "
            "for any question that needs case data. Supports filtering by "
            "district, crime type, date range, accused name, and semantic "
            "similarity search on case descriptions/MO."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why you're calling this agent for this query",
                }
            },
            "required": ["reason"],
        },
    },
    {
        "name": "link_agent",
        "description": (
            "Build a criminal network graph showing who is connected to whom "
            "and through what (same address, phone, co-accused, narrative "
            "mention). Use this when the question asks about connections, "
            "associates, networks, or relationships between people. "
            "REQUIRES query_agent to have run first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why you're calling this agent",
                }
            },
            "required": ["reason"],
        },
    },
    {
        "name": "trend_agent",
        "description": (
            "Analyze crime patterns over time and location — spot spikes, "
            "trends, hotspots, and recurring MO patterns. Use this when "
            "the question asks about trends, patterns, increases, decreases, "
            "hotspots, or 'is this getting worse'. "
            "REQUIRES query_agent to have run first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why you're calling this agent",
                }
            },
            "required": ["reason"],
        },
    },
    {
        "name": "risk_agent",
        "description": (
            "Produce a risk assessment combining network analysis and trend "
            "data into an explainable score (Low/Medium/High). Use this when "
            "the question asks about risk, danger, likelihood of reoffense, "
            "or 'should we expect more'. "
            "REQUIRES both link_agent AND trend_agent to have run first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why you're calling this agent",
                }
            },
            "required": ["reason"],
        },
    },
]


# ===================================================================
# DEPENDENCY RULES — enforced regardless of what Gemini decides
# ===================================================================

DEPENDENCIES = {
    "query_agent": [],                          # no prerequisites
    "link_agent": ["query_agent"],              # needs records first
    "trend_agent": ["query_agent"],             # needs records first
    "risk_agent": ["link_agent", "trend_agent"],  # needs both
}

AGENT_FUNCTIONS = {
    "query_agent": query_agent,
    "link_agent": link_agent,
    "trend_agent": trend_agent,
    "risk_agent": risk_agent,
}


# ===================================================================
# SYSTEM PROMPT — tells Gemini its role and constraints
# ===================================================================

SYSTEM_PROMPT = """You are KIRAN — Karnataka Investigative Reasoning and Analysis Node — the central orchestration intelligence of the KSP Crime AI Platform. You are a goal-based investigative planner, not a chatbot.

## Your Role
You coordinate a team of four specialist agents to answer investigator queries against the Karnataka State Police crime database. You do NOT answer questions yourself — you reason about what information is needed, then route to the correct specialist agent(s) to gather it.

## Your Specialist Agents

query_agent:
  Does: Fetches matching crime records from the database — filtered by district, crime type, accused name, date range, or semantic MO similarity search.
  Use when: The question needs any case data. ALWAYS run this first, before any other agent.

link_agent:
  Does: Builds a criminal network graph mapping who is connected to whom via co-accused records, shared locations, or narrative co-mentions.
  Use when: The question involves connections, associates, networks, kingpins, or relationships between people. Requires query_agent to have run first.

trend_agent:
  Does: Identifies temporal spikes, geographical hotspots, recurring MO patterns, and crime escalation over time.
  Use when: The question involves trends, patterns, spikes, time periods, hotspots, or "is crime increasing". Requires query_agent to have run first.

risk_agent:
  Does: Computes an explainable risk score (Low/Medium/High) combining network density and trend severity into an actionable threat assessment.
  Use when: The question involves risk, likelihood of reoffense, threat level, or predictive enforcement. Requires BOTH link_agent AND trend_agent to have run first.

## How You Reason (ReAct Protocol)
For every investigator question, follow this sequence:
  1. PARSE — What exactly is the investigator trying to find out? Decompose into specific information needs.
  2. MAP — Which agents produce the data that covers each information need?
  3. ORDER — Enforce hard dependency rules before selecting the call sequence.
  4. EVALUATE — After each agent round: "Does the collected data fully answer the original question?" If yes → DONE. If no → plan the next round.
  5. LIMIT — Never exceed 3 planning rounds. Stop when the core question is answerable.

## Dependency Rules (Absolute — Never Break)
- query_agent has no prerequisites. It always runs first.
- link_agent requires query_agent to have completed first.
- trend_agent requires query_agent to have completed first.
- risk_agent requires BOTH link_agent AND trend_agent to have completed first.
- Never call the same agent twice in one session.

## Agent Selection Guide
- Question about a specific person → query_agent + link_agent
- Question about a time period, spike, or trend → query_agent + trend_agent
- Question about risk or threat level → query_agent + link_agent + trend_agent + risk_agent
- Simple lookup (case count, district filter) → query_agent only
- General statistics question (who committed most crimes, top crime type) → query_agent only; the Composer handles aggregation

## Anti-Patterns to Avoid
- Do NOT skip query_agent, even if the question seems non-record-specific.
- Do NOT call risk_agent without link_agent and trend_agent having run first.
- Do NOT run agents unnecessarily. Precision over completeness.
- Do NOT over-plan. If the data available answers the question, say DONE.

Respond with the name(s) of the agent(s) to call next. When sufficient data has been gathered, respond with exactly: DONE"""


# ===================================================================
# PLANNER — the ReAct loop
# ===================================================================

def build_state_summary(state: dict) -> str:
    """
    Summarize current state for Gemini to evaluate.
    This is what Gemini sees after each round to decide "enough or more?"
    """
    summary_parts = []

    records = state.get("records_found")
    if records:
        summary_parts.append(f"- query_agent: found {len(records)} records")

    entities = state.get("entities_found")
    edges = state.get("network_edges")
    if entities is not None:
        summary_parts.append(
            f"- link_agent: {len(entities)} entities, {len(edges or [])} connections"
        )

    trends = state.get("trend_findings")
    if trends is not None:
        spikes = sum(1 for t in trends if t.get("is_spike"))
        summary_parts.append(
            f"- trend_agent: {len(trends)} data points, {spikes} spikes"
        )

    risk = state.get("risk_assessment")
    if risk:
        summary_parts.append(
            f"- risk_agent: score={risk['score']}, band={risk['band']}"
        )

    if not summary_parts:
        return "No agents have run yet."

    return "Current findings:\n" + "\n".join(summary_parts)


def resolve_dependencies(requested_agents: list[str], completed: set[str]) -> list[str]:
    """
    Given the agents Gemini wants to call, figure out the correct
    execution order, inserting any missing prerequisites.
    
    Example: Gemini asks for risk_agent but link_agent hasn't run yet
    → we insert link_agent (and query_agent if needed) before it.
    """
    execution_order = []
    to_process = list(requested_agents)

    while to_process:
        agent = to_process.pop(0)
        if agent in completed or agent in execution_order:
            continue

        # Check if prerequisites are met
        deps = DEPENDENCIES.get(agent, [])
        unmet = [d for d in deps if d not in completed and d not in execution_order]

        if unmet:
            # Insert prerequisites first, then re-add this agent
            to_process = unmet + [agent] + to_process
        else:
            execution_order.append(agent)

    return execution_order


def planner_agent(state: dict) -> dict:
    """
    Planner Agent — the ReAct orchestrator.

    Reads:  state["resolved_query"]     — the investigator's question
            state["conversation_history"] — last few turns (optional)
            state["dataset"]            — loaded dataset

    Writes: state (modified by whichever agents it calls)
            state["planner_log"]        — audit trail of decisions
            state["agents_used"]        — list of agents that ran

    TECHNIQUE: ReAct loop
      1. REASON: Ask Gemini which agents to call
      2. ACT:    Execute those agents (with dependency ordering)
      3. OBSERVE: Check what came back
      4. LOOP:   Ask Gemini "enough?" — if no, go to step 1
      Max 3 iterations to prevent infinite loops.
    """
    query = state.get("resolved_query", "")
    history = state.get("conversation_history", [])

    print(f"\n{'='*60}")
    print(f"[Planner] Question: {query}")
    print(f"{'='*60}")

    # Track what has run and planning decisions
    completed_agents = set()
    planner_log = []
    max_iterations = 3

    # --- GEMINI-POWERED PATH ---
    if GEMINI_AVAILABLE and (os.environ.get("GEMINI_API_KEY_PLANNER") or os.environ.get("GEMINI_API_KEY")):
        try:
            model = get_generative_model(
                "gemini-3.1-flash-lite",
                system_instruction=SYSTEM_PROMPT,
                api_key_env_var="GEMINI_API_KEY_PLANNER"
            )
        except Exception as e:
            print(f"[Planner] Failed to initialize model: {e}")
            model = None

        if not model:
            print("[Planner] Falling back to rule-based planning...")
            state = _rule_based_plan(state, query, completed_agents, planner_log)
            state["planner_log"] = planner_log
            state["agents_used"] = list(completed_agents)
            return state

        for iteration in range(max_iterations):
            print(f"\n[Planner] --- Iteration {iteration + 1} ---")

            # Build the prompt with current state
            state_summary = build_state_summary(state)
            history_text = ""
            if history:
                history_text = "\nRecent conversation:\n" + "\n".join(
                    f"  {turn['role']}: {turn['text']}" for turn in history[-3:]
                )

            prompt = (
                f"Investigator's question: \"{query}\"\n"
                f"{history_text}\n\n"
                f"{state_summary}\n\n"
                f"Which agent(s) should run next? Or is this DONE?\n"
                f"Reply with a JSON object: "
                f'{{"agents": ["agent_name", ...], "reasoning": "...", "done": true/false}}'
            )

            try:
                # Option 5: 3-second delay before Gemini call to avoid
                # exceeding the free-tier per-minute rate limit
                time.sleep(3)
                response = model.generate_content(prompt)
                response_text = response.text.strip()

                # Parse Gemini's decision
                # Try to extract JSON from the response
                json_match = None
                # Look for JSON in code block
                import re
                code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
                if code_block:
                    json_match = code_block.group(1)
                else:
                    # Try direct JSON parse
                    brace_start = response_text.find("{")
                    brace_end = response_text.rfind("}") + 1
                    if brace_start >= 0 and brace_end > brace_start:
                        json_match = response_text[brace_start:brace_end]

                if json_match:
                    decision = json.loads(json_match)
                else:
                    # Fallback: if Gemini says DONE
                    if "done" in response_text.lower():
                        decision = {"agents": [], "reasoning": response_text, "done": True}
                    else:
                        decision = {"agents": ["query_agent"], "reasoning": "defaulting to query", "done": False}

                print(f"[Planner] Gemini decided: {decision}")

                planner_log.append({
                    "iteration": iteration + 1,
                    "decision": decision,
                    "state_summary": state_summary,
                })

                if decision.get("done", False) and completed_agents:
                    print("[Planner] Gemini says: DONE — enough info to answer.")
                    break

                # Resolve dependencies and execute
                requested = decision.get("agents", [])
                if not requested and not decision.get("done"):
                    requested = ["query_agent"]

                execution_order = resolve_dependencies(requested, completed_agents)

                for agent_name in execution_order:
                    if agent_name in AGENT_FUNCTIONS:
                        print(f"[Planner] Executing: {agent_name}")
                        state = AGENT_FUNCTIONS[agent_name](state)
                        completed_agents.add(agent_name)
                    else:
                        print(f"[Planner] Unknown agent: {agent_name}, skipping")

            except Exception as e:
                print(f"[Planner] Gemini error: {e}")
                print("[Planner] Falling back to rule-based planning...")
                # Fall through to rule-based path
                state = _rule_based_plan(state, query, completed_agents, planner_log)
                break

    else:
        # --- RULE-BASED FALLBACK (no Gemini API key) ---
        print("[Planner] No Gemini API key — using rule-based planning")
        state = _rule_based_plan(state, query, completed_agents, planner_log)

    # --- Force run link_agent if query_agent ran and found records ---
    # This guarantees that the syndicate map is always dynamically updated and populated
    if "query_agent" in completed_agents and state.get("records_found") and "link_agent" not in completed_agents:
        print("[Planner] Force running link_agent to generate the dynamic syndicate network graph.")
        state = link_agent(state)
        completed_agents.add("link_agent")

    # --- Final state updates ---
    state["planner_log"] = planner_log
    state["agents_used"] = list(completed_agents)

    print(f"\n[Planner] Finished. Agents used: {list(completed_agents)}")
    return state


# ===================================================================
# RULE-BASED FALLBACK — works without Gemini
# ===================================================================
# If no API key is set, use keyword matching to decide which agents
# to run. Less smart than Gemini but fully functional for testing.
# ===================================================================

# Keywords that suggest each agent is needed
AGENT_KEYWORDS = {
    "link_agent": [
        "connect", "associate", "network", "linked", "relationship",
        "co-accused", "gang", "accomplice", "who else", "related to",
        "together", "same person", "involved with",
    ],
    "trend_agent": [
        "trend", "pattern", "increase", "decrease", "spike", "rise",
        "hotspot", "growing", "more cases", "getting worse", "statistics",
        "frequency", "over time", "monthly", "weekly",
    ],
    "risk_agent": [
        "risk", "danger", "expect more", "forecast", "predict",
        "likely", "probability", "should we worry", "threat",
        "reoffend", "repeat", "future",
    ],
}


def _rule_based_plan(
    state: dict,
    query: str,
    completed: set,
    log: list,
) -> dict:
    """
    Decide which agents to run based on keyword matching.
    Always runs query_agent. Adds others if keywords match.
    """
    query_lower = query.lower()

    # Step 1: ALWAYS run query agent first
    if "query_agent" not in completed:
        print("[Planner-RuleBased] Running query_agent (always first)")
        state = query_agent(state)
        completed.add("query_agent")
        log.append({
            "iteration": 1,
            "decision": {"agents": ["query_agent"], "reasoning": "always runs first", "done": False},
        })

    # Step 2: Check which other agents are needed
    needed = []
    for agent_name, keywords in AGENT_KEYWORDS.items():
        if any(kw in query_lower for kw in keywords):
            needed.append(agent_name)

    # If nothing specific matched, run link + trend by default
    # (better to have extra info than miss something)
    if not needed:
        needed = ["link_agent", "trend_agent"]

    # Step 3: Resolve dependencies and execute
    execution_order = resolve_dependencies(needed, completed)

    for agent_name in execution_order:
        if agent_name in AGENT_FUNCTIONS and agent_name not in completed:
            print(f"[Planner-RuleBased] Running {agent_name}")
            state = AGENT_FUNCTIONS[agent_name](state)
            completed.add(agent_name)

    log.append({
        "iteration": 2,
        "decision": {
            "agents": list(completed),
            "reasoning": f"keyword-matched: {needed}",
            "done": True,
        },
    })

    return state

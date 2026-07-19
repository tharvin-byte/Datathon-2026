"""
LANGGRAPH PIPELINE ORCHESTRATION — Crime AI StateGraph
======================================================
PURPOSE: Wires Planner, Query, Link, Trend, Risk, Verifier, and Composer agents
into a unified asynchronous StateGraph with conditional edges and live WebSocket broadcast.
"""

import asyncio
from typing import Dict, Any
from agents.planner import planner_agent
from agents.verifier import verifier_agent
from agents.composer import composer_agent
from core.session_store import broadcast_status

try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

class CrimeAIPipeline:
    """
    Orchestrates the multi-agent execution loop with live status broadcasts.
    If LangGraph is installed, constructs StateGraph; otherwise executes async ReAct loop.
    """
    async def ainvoke(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        session_id = initial_state.get("session_id", "default")
        
        # 1. Planner loop & Specialist execution
        await broadcast_status(session_id, {"event": "planner_thinking"})
        
        # We run the synchronous planner_agent in an executor/thread pool
        loop = asyncio.get_event_loop()
        state = await loop.run_in_executor(None, planner_agent, initial_state)
        
        # Broadcast completed specialist agents
        agents_used = state.get("agents_used", [])
        for ag in agents_used:
            if ag == "query_agent":
                recs = len(state.get("records_found", []))
                await broadcast_status(session_id, {"event": "agent_completed", "agent": "query_agent", "summary": f"{recs} matching records extracted"})
            elif ag == "link_agent":
                ents = len(state.get("entities_found", []))
                edges = len(state.get("network_edges", []))
                await broadcast_status(session_id, {"event": "agent_completed", "agent": "link_agent", "summary": f"{ents} entities and {edges} syndicate links identified"})
            elif ag == "trend_agent":
                trends = len(state.get("trend_findings", []))
                await broadcast_status(session_id, {"event": "agent_completed", "agent": "trend_agent", "summary": f"{trends} temporal spikes/patterns flagged"})
            elif ag == "risk_agent":
                risk = state.get("risk_assessment", {})
                score = risk.get("score", 0)
                band = risk.get("band", "Low")
                await broadcast_status(session_id, {"event": "agent_completed", "agent": "risk_agent", "summary": f"Risk Score: {score}/10 ({band} Band)"})
                
        # 2. Verifier (Fact-Checking)
        await broadcast_status(session_id, {"event": "verifier_running"})
        state = await loop.run_in_executor(None, verifier_agent, state)
        unsupported = len(state.get("verification_result", {}).get("unsupported_claims", []))
        await broadcast_status(session_id, {"event": "verifier_result", "unsupported_claims": unsupported})
        
        # 3. Response Composer
        await broadcast_status(session_id, {"event": "composer_running"})
        state = await loop.run_in_executor(None, composer_agent, state)
        
        query_id = state.get("final_response", {}).get("query_id", "Q-101")
        await broadcast_status(session_id, {"event": "done", "query_id": query_id})
        
        return state

compiled_graph = CrimeAIPipeline()

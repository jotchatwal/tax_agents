import logging
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, START, END

from backend.app.graph.state import AgentState
from backend.app.graph.nodes import (
    node_authenticate_and_authorize,
    node_classify_intent,
    node_load_profile,
    node_retrieve_memories,
    node_detect_conflicts,
    node_retrieve_tax_rules,
    node_route_agents,
    node_persist_changes,
    node_format_response
)

logger = logging.getLogger(__name__)

def build_taxpilot_graph():
    graph = StateGraph(AgentState)

    # Add Nodes - now includes the route_agents node that delegates to
    # TaxAnalysisAgent and OpportunityResearchAgent
    graph.add_node("authenticate", node_authenticate_and_authorize)
    graph.add_node("classify_intent", node_classify_intent)
    graph.add_node("load_profile", node_load_profile)
    graph.add_node("retrieve_memories", node_retrieve_memories)
    graph.add_node("detect_conflicts", node_detect_conflicts)
    graph.add_node("retrieve_rules", node_retrieve_tax_rules)
    graph.add_node("route_agents", node_route_agents)
    graph.add_node("persist_changes", node_persist_changes)
    graph.add_node("format_response", node_format_response)

    # Edges: authenticate -> classify -> load profile -> retrieve memories
    #   -> detect conflicts -> retrieve rules -> route to agents
    #   -> persist -> format response
    graph.add_edge(START, "authenticate")
    graph.add_edge("authenticate", "classify_intent")
    graph.add_edge("classify_intent", "load_profile")
    graph.add_edge("load_profile", "retrieve_memories")
    graph.add_edge("retrieve_memories", "detect_conflicts")
    graph.add_edge("detect_conflicts", "retrieve_rules")
    graph.add_edge("retrieve_rules", "route_agents")
    graph.add_edge("route_agents", "persist_changes")
    graph.add_edge("persist_changes", "format_response")
    graph.add_edge("format_response", END)

    return graph.compile()

taxpilot_orchestrator = build_taxpilot_graph()

def run_taxpilot_workflow(user_id: str, request: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Execute the end-to-end LangGraph workflow with two specialized agents."""
    initial_state: AgentState = {
        "user_id": user_id,
        "session_id": session_id or "default_session",
        "request": request,
        "intent": "",
        "consent_verified": False,
        "profile": None,
        "retrieved_memories": [],
        "proposed_memory_changes": [],
        "tax_rules": [],
        "analysis": {},
        "calculations": {},
        "eligibility_results": [],
        "recommendations": [],
        "missing_information": [],
        "approval_required": False,
        "audit_events": [],
        "final_response": {},
        "error": None
    }

    result = taxpilot_orchestrator.invoke(initial_state)
    return result["final_response"]

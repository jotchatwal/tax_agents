from typing import TypedDict, List, Dict, Any, Optional

class AgentState(TypedDict):
    user_id: str
    session_id: str
    request: str
    intent: str  # onboarding, question, profile_update, scenario, memory_governance
    consent_verified: bool
    profile: Optional[Dict[str, Any]]
    retrieved_memories: List[Dict[str, Any]]
    proposed_memory_changes: List[Dict[str, Any]]
    tax_rules: List[Dict[str, Any]]
    analysis: Dict[str, Any]
    calculations: Dict[str, Any]
    eligibility_results: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    missing_information: List[str]
    approval_required: bool
    audit_events: List[Dict[str, Any]]
    final_response: Dict[str, Any]
    error: Optional[str]

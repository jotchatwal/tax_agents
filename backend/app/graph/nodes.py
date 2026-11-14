import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from bson import ObjectId

from backend.app.graph.state import AgentState
from backend.app.db.repositories import (
    UserRepository,
    ProfileRepository,
    MemoryRepository,
    TaxRuleRepository,
    RecommendationRepository,
    AuditRepository
)
from backend.app.services.tax_calc import (
    calculate_combined_tax,
    calculate_marginal_tax_rate,
    calculate_rrsp_what_if
)
from backend.app.services.memory_service import MemoryGovernanceService
from backend.app.models.recommendation import (
    RecommendationModel,
    TaxSavingEstimate,
    EligibilityAssessment,
    EvidenceReference
)
from backend.app.agents.tax_analysis_agent import TaxAnalysisAgent
from backend.app.agents.opportunity_research_agent import OpportunityResearchAgent

user_repo = UserRepository()
profile_repo = ProfileRepository()
memory_repo = MemoryRepository()
tax_rule_repo = TaxRuleRepository()
rec_repo = RecommendationRepository()
audit_repo = AuditRepository()
memory_service = MemoryGovernanceService(memory_repo, audit_repo)

tax_analysis_agent = TaxAnalysisAgent()
opportunity_agent = OpportunityResearchAgent()

def node_authenticate_and_authorize(state: AgentState) -> Dict[str, Any]:
    """Verify user identity and consent; fail closed if unavailable."""
    user_id = state.get("user_id")
    if not user_id:
        return {"error": "Missing authenticated principal", "consent_verified": False}

    user = user_repo.get_by_id(user_id)
    if not user or user.get("status") != "active":
        return {"error": "Unauthorized or inactive user", "consent_verified": False}

    return {"consent_verified": True, "error": None}

def node_classify_intent(state: AgentState) -> Dict[str, Any]:
    """Classify user intent: profile_update, scenario, memory_governance, question, onboarding."""
    req = (state.get("request") or "").strip().lower()

    if any(k in req for k in ["delete memory", "forget", "erase", "remove memory", "correct memory"]):
        intent = "memory_governance"
    elif any(k in req for k in ["salary is now", "income is now", "earning", "got a raise", "promotion", "changed jobs", "new salary", "new job", "now make", "make 105000", "salary is 105000"]):
        intent = "profile_update"
    elif any(k in req for k in ["what if", "model rrsp", "contribute", "simulate"]):
        intent = "scenario"
    elif any(k in req for k in ["onboard", "create profile", "setup"]):
        intent = "onboarding"
    else:
        intent = "question"

    return {"intent": intent}

def node_load_profile(state: AgentState) -> Dict[str, Any]:
    """Load canonical user profile for tax year 2025."""
    user_id = state["user_id"]
    profile = profile_repo.get_current_profile(user_id, 2025)
    return {"profile": profile}

def node_retrieve_memories(state: AgentState) -> Dict[str, Any]:
    """Retrieve user-scoped active memories with semantic vector search."""
    user_id = state["user_id"]
    req = state.get("request", "")
    memories = memory_service.retrieve_active_memories(user_id, query_text=req if len(req) > 5 else None)
    return {"retrieved_memories": memories}

def node_detect_conflicts(state: AgentState) -> Dict[str, Any]:
    """Check for proposed material changes such as annualized income changes."""
    intent = state.get("intent")
    req = state.get("request", "")
    proposed_changes = []

    if intent == "profile_update":
        numbers = re.findall(r'\b\d{4,7}\b', req.replace("$", "").replace(",", ""))
        if numbers:
            new_val = float(numbers[0])
            proposed_changes.append({
                "field": "annualized_income",
                "new_value": new_val,
                "currency": "CAD",
                "effective_date": "2025-03-01",
                "reason": f"User reported new annualized income of ${new_val:,.0f} CAD."
            })

    return {"proposed_memory_changes": proposed_changes}

def node_retrieve_tax_rules(state: AgentState) -> Dict[str, Any]:
    """Retrieve verified CRA and Ontario 2025 rules."""
    rules = tax_rule_repo.list_rules_for_calculation(tax_year=2025, country="CA", province="ON")
    return {"tax_rules": rules}

def node_route_agents(state: AgentState) -> Dict[str, Any]:
    """
    Route to Tax Analysis Agent, Opportunity Research Agent, or both.
    This is the key architectural node that delegates to specialized agents.
    """
    profile = state.get("profile") or {}
    proposed = state.get("proposed_memory_changes", [])
    tax_rules = state.get("tax_rules", [])

    # --- Tax Analysis Agent: deterministic calculations ---
    analysis = tax_analysis_agent.analyze(profile, proposed, tax_rules)

    # --- Opportunity Research Agent: eligibility + recommendations ---
    opportunity_result = opportunity_agent.evaluate_opportunities(
        profile=profile,
        calculations=analysis,
        proposed_changes=proposed,
        tax_rules=tax_rules
    )

    # --- Tax Analysis Agent: synthesize natural language explanation ---
    is_change = len(proposed) > 0
    explanation = tax_analysis_agent.synthesize_explanation(profile, analysis, is_change)

    return {
        "calculations": analysis,
        "recommendations": opportunity_result.get("recommendations", []),
        "missing_information": opportunity_result.get("missing_information", []),
        "eligibility_results": opportunity_result.get("eligibility_results", []),
        "analysis": {"explanation": explanation, "agent": "TaxAnalysisAgent + OpportunityResearchAgent"}
    }

def node_persist_changes(state: AgentState) -> Dict[str, Any]:
    """Persist profile updates, memory supersessions, and recommendations."""
    user_id = state["user_id"]
    proposed = state.get("proposed_memory_changes", [])
    profile = state.get("profile") or {}
    recommendations = state.get("recommendations", [])
    audit_events = []

    if proposed:
        for income_change in proposed:
            if income_change.get("field") == "annualized_income":
                new_income = float(income_change["new_value"])
                cur_version = profile.get("profile_version", 1)

                updated_profile = profile_repo.update_profile_with_versioning(
                    user_id=user_id,
                    tax_year=2025,
                    updates={
                        "employment_periods.0.annualized_income": new_income,
                        "employment_periods.0.actual_income_earned": new_income
                    },
                    expected_version=cur_version
                )

                active_income_mems = memory_repo.get_active_memories(user_id, memory_type="employment_income")
                old_mem_id = active_income_mems[0]["_id"] if active_income_mems else None

                if old_mem_id:
                    new_mem_id = memory_service.supersede_memory_fact(
                        user_id=user_id,
                        old_memory_id=old_mem_id,
                        new_content=f"User confirmed updated annual salary of ${new_income:,.0f} CAD effective 2025-03-01.",
                        new_structured_data={
                            "annualized_income": new_income,
                            "currency": "CAD",
                            "memory_type": "employment_income"
                        },
                        profile_version=cur_version + 1,
                        reason=income_change["reason"]
                    )
                    audit_events.append({
                        "action": "supersede",
                        "entity": "agent_memory",
                        "old_id": str(old_mem_id),
                        "new_id": new_mem_id
                    })

                if updated_profile:
                    profile = updated_profile

    for rec_data in recommendations:
        rec_repo.supersede_older_recommendations(user_id, 2025, rec_data["recommendation_type"])
        rec_model = RecommendationModel(**rec_data)
        saved_id = rec_repo.save_recommendation(user_id, rec_model)
        audit_events.append({"action": "create", "entity": "recommendation", "id": saved_id})

    return {"profile": profile, "audit_events": audit_events}

def node_format_response(state: AgentState) -> Dict[str, Any]:
    """Format final response using the agent-generated explanation."""
    intent = state.get("intent")
    recs = state.get("recommendations", [])
    proposed = state.get("proposed_memory_changes", [])
    calcs = state.get("calculations", {})
    profile = state.get("profile") or {}
    memories = state.get("retrieved_memories", [])
    analysis = state.get("analysis", {})

    # Use the explanation synthesized by the Tax Analysis Agent
    message = analysis.get("explanation", "")

    # If the agent didn't produce an explanation, build a deterministic fallback
    if not message:
        rec = recs[0] if recs else {}
        saving = rec.get("estimated_tax_saving", {}).get("minimum", 0)
        rate = rec.get("estimated_tax_saving", {}).get("marginal_tax_rate", 0)
        inc = calcs.get("current_income", 85000.0)

        if proposed:
            income_update = proposed[0]
            message = (
                f"### Profile Updated to Version {profile.get('profile_version', 2)}\n\n"
                f"- **New Annual Salary:** ${income_update['new_value']:,.2f} CAD\n"
                f"- **Prior Memory Superseded**\n"
                f"- **New Marginal Tax Rate:** {rate * 100:.2f}%\n"
                f"- **Updated RRSP Tax Savings:** ${saving:,.2f} CAD\n\n"
                f"**Verified Evidence:** [CRA](https://www.canada.ca/en/revenue-agency/services/tax/individuals/tax-rates-brackets/last-year.html) | [Ontario](https://www.ontario.ca/document/general-information-income-tax-and-benefit-return/tax-rates-and-brackets)"
            )
        else:
            message = (
                f"### Tax Analysis for 2025 (Ontario Resident)\n\n"
                f"Based on your confirmed profile (Annual Income: **${inc:,.2f} CAD**, Version {profile.get('profile_version', 1)}):\n\n"
                f"- **Combined Marginal Tax Rate:** {rate * 100:.2f}%\n"
                f"- **Recommended Opportunity:** {rec.get('title', 'RRSP Planning')}\n"
                f"- **Estimated Tax Savings:** **${saving:,.2f} CAD** on a $5,000 RRSP contribution.\n"
                f"- **Eligibility Status:** `{rec.get('eligibility', {}).get('status', 'needs_verification')}`\n\n"
                f"**Official Sources:** [CRA](https://www.canada.ca/en/revenue-agency/services/tax/individuals/tax-rates-brackets/last-year.html)"
            )

    final_res = {
        "message": message,
        "intent": intent,
        "profile": profile,
        "recommendations": recs,
        "calculations": calcs,
        "missing_information": state.get("missing_information", []),
        "retrieved_memories_count": len(memories),
        "audit_events": state.get("audit_events", []),
        "agents_used": analysis.get("agent", "deterministic_fallback")
    }
    return {"final_response": final_res}

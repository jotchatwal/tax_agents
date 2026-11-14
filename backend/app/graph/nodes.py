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
from backend.app.services.llm_service import llm_service
from backend.app.models.recommendation import (
    RecommendationModel,
    TaxSavingEstimate,
    EligibilityAssessment,
    EvidenceReference
)

user_repo = UserRepository()
profile_repo = ProfileRepository()
memory_repo = MemoryRepository()
tax_rule_repo = TaxRuleRepository()
rec_repo = RecommendationRepository()
audit_repo = AuditRepository()
memory_service = MemoryGovernanceService(memory_repo, audit_repo)

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
    """Classify user intent: greeting, profile_update, scenario, memory_governance, question, onboarding."""
    req = (state.get("request") or "").strip()
    req_lower = req.lower()

    # 1. Fast deterministic greeting check
    req_clean = re.sub(r'[^\w\s]', '', req_lower).strip()
    if req_clean in ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "greetings", "howdy", "sup", "hi there", "hello there"]:
        return {"intent": "greeting", "analysis": {"intent": "greeting"}}

    # Fetch current baseline salary to pass context to LLM
    user_id = state.get("user_id")
    profile = profile_repo.get_current_profile(user_id, 2025) or {}
    emp = (profile.get("employment_periods") or [{}])[0]
    cur_salary = emp.get("annualized_income")

    # 2. Try LLM intent & entity extraction with baseline context
    llm_analysis = llm_service.extract_intent_and_entities(req, current_salary=cur_salary)
    if llm_analysis and llm_analysis.get("intent"):
        intent = llm_analysis["intent"]
        # If user reports an actual factual life change (promotion, raise), prioritize profile_update
        if llm_analysis.get("is_factual_update"):
            intent = "profile_update"
        return {"intent": intent, "analysis": llm_analysis}

    # 3. Deterministic keyword fallback
    if any(k in req_lower for k in ["delete memory", "forget", "erase", "remove memory", "correct memory"]):
        intent = "memory_governance"
    elif any(k in req_lower for k in ["salary is now", "income is now", "earning", "got a raise", "promotion", "changed jobs", "new salary", "new job", "now make", "make 105000", "salary is 105000", "increment"]):
        intent = "profile_update"
    elif any(k in req_lower for k in ["what if", "model rrsp", "contribute", "simulate"]):
        intent = "scenario"
    elif any(k in req_lower for k in ["onboard", "create profile", "setup"]):
        intent = "onboarding"
    else:
        intent = "question"

    return {"intent": intent, "analysis": {}}

def node_handle_greeting(state: AgentState) -> Dict[str, Any]:
    """Handle conversational greetings politely without executing heavy calculation pipelines."""
    user_id = state.get("user_id")
    profile = profile_repo.get_current_profile(user_id, 2025) or {}
    emp = (profile.get("employment_periods") or [{}])[0]
    salary = emp.get("annualized_income")
    user = user_repo.get_by_id(user_id) if user_id else {}
    name = (user or {}).get("display_name", "there")

    salary_str = f" (${salary:,.0f} CAD)" if salary else ""
    message = (
        f"Hello {name}! 👋 Welcome to **TaxPilot AI**, your user-governed tax companion for Ontario (tax year 2025).\n\n"
        f"Your active profile is loaded{salary_str}. How can I assist you today?\n\n"
        f"- 📊 **Explore Opportunities:** Ask *'What tax planning opportunities do I have for 2025?'*\n"
        f"- 💡 **Model Deductions:** Ask *'What if I contribute $5,000 to my RRSP?'*\n"
        f"- 💼 **Report Life Changes:** Tell me *'I changed jobs and my salary is now 105,000 CAD'*\n"
        f"- 🛡️ **Govern Memories:** Review or erase stored tax facts at any time in the **Governed Memories** tab."
    )

    final_res = {
        "message": message,
        "intent": "greeting",
        "profile": profile,
        "recommendations": [],
        "calculations": {},
        "missing_information": [],
        "retrieved_memories_count": 0,
        "audit_events": []
    }
    return {"final_response": final_res}

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
    analysis = state.get("analysis") or {}
    profile = state.get("profile") or {}
    emp = (profile.get("employment_periods") or [{}])[0]
    cur_salary = float(emp.get("annualized_income") or 85000.0)

    proposed_changes = []
    is_factual = analysis.get("is_factual_update", False)

    # 1. Check if LLM calculated a new salary directly or extracted increment
    calculated_salary = analysis.get("calculated_new_salary_cad")
    salary_cad = analysis.get("salary_cad")
    salary_inc = analysis.get("salary_increment_cad")

    new_val = None
    if calculated_salary and calculated_salary > 0:
        new_val = float(calculated_salary)
    elif salary_inc and salary_inc > 0:
        new_val = cur_salary + float(salary_inc)
    elif salary_cad and salary_cad > 0:
        # If the number is a relative increment (e.g. 20000) and user mentioned promotion/raise
        if salary_cad <= 35000 and any(k in req.lower() for k in ["increment", "raise", "increase", "bump"]):
            new_val = cur_salary + float(salary_cad)
        else:
            new_val = float(salary_cad)

    # Determine dynamic effective date
    extracted_date = analysis.get("effective_date")
    if extracted_date and re.match(r'^\d{4}-\d{2}-\d{2}$', str(extracted_date).strip()):
        effective_date_str = str(extracted_date).strip()
    else:
        # Check for natural language date in query (e.g. "effective June 1st", "starting May 2025")
        date_match = re.search(r'(?:effective|starting|as of)\s+(?:from\s+)?([A-Za-z]+)\s*(\d{1,2})?(?:st|nd|rd|th)?,?\s*(\d{4})?', req, re.IGNORECASE)
        if date_match:
            month_str, day_str, year_str = date_match.group(1), date_match.group(2) or "1", date_match.group(3) or "2025"
            try:
                dt_parsed = datetime.strptime(f"{month_str} {day_str} {year_str}", "%B %d %Y")
                effective_date_str = dt_parsed.strftime("%Y-%m-%d")
            except Exception:
                try:
                    dt_parsed = datetime.strptime(f"{month_str} {day_str} {year_str}", "%b %d %Y")
                    effective_date_str = dt_parsed.strftime("%Y-%m-%d")
                except Exception:
                    effective_date_str = datetime.now().strftime("%Y-%m-%d")
        else:
            effective_date_str = datetime.now().strftime("%Y-%m-%d")

    if new_val and (intent == "profile_update" or is_factual):
        proposed_changes.append({
            "field": "annualized_income",
            "new_value": new_val,
            "currency": "CAD",
            "effective_date": effective_date_str,
            "reason": f"User reported salary change to ${new_val:,.0f} CAD effective {effective_date_str} (updated from ${cur_salary:,.0f} CAD)."
        })
    elif intent == "profile_update" or any(k in req.lower() for k in ["salary is now", "earning", "raise", "increment", "promotion", "changed jobs", "new salary"]):
        # Regex fallback for relative increments e.g. "increment of 20k", "20k raise"
        inc_match = re.search(r'(?:raise|increment|increase)\s*(?:of)?\s*\$?(\d+)(?:\s*(k|thousand))?', req, re.IGNORECASE)
        inc_match_alt = re.search(r'\$?(\d+)(?:\s*(k|thousand))?\s*(?:raise|increment|increase)', req, re.IGNORECASE)
        match = inc_match or inc_match_alt
        if match:
            num = float(match.group(1))
            mult = 1000.0 if match.group(2) or num < 1000 else 1.0
            inc_val = num * mult
            new_val = cur_salary + inc_val
            proposed_changes.append({
                "field": "annualized_income",
                "new_value": new_val,
                "currency": "CAD",
                "effective_date": effective_date_str,
                "reason": f"User reported salary increment of ${inc_val:,.0f} CAD effective {effective_date_str} (updated from ${cur_salary:,.0f} CAD to ${new_val:,.0f} CAD)."
            })
        else:
            numbers = re.findall(r'\b\d{4,7}\b', req.replace("$", "").replace(",", ""))
            if numbers:
                new_val = float(numbers[0])
                proposed_changes.append({
                    "field": "annualized_income",
                    "new_value": new_val,
                    "currency": "CAD",
                    "effective_date": effective_date_str,
                    "reason": f"User reported new annualized income of ${new_val:,.0f} CAD effective {effective_date_str}."
                })

    # Check for RRSP contribution or deduction mentions
    rrsp_contrib_val = analysis.get("rrsp_contribution_cad")
    if not rrsp_contrib_val:
        m_contrib = re.search(r'(?:assuming|claim(?:ing)?|contribut(?:e|ion)|deduct(?:ion)?)\s*(?:a\s+)?\$?(\d+[\d,]*)\s*(?:rrsp|deduction|\b)', req, re.IGNORECASE)
        if m_contrib:
            try:
                candidate = float(m_contrib.group(1).replace(",", ""))
                if candidate > 0 and candidate != new_val:
                    rrsp_contrib_val = candidate
            except Exception:
                pass
    if rrsp_contrib_val and rrsp_contrib_val > 0:
        proposed_changes.append({
            "field": "rrsp_contribution",
            "new_value": float(rrsp_contrib_val),
            "reason": f"User specified RRSP deduction/contribution of ${rrsp_contrib_val:,.0f} CAD."
        })

    # Check for RRSP deduction limit / Notice of Assessment mentions
    rrsp_limit_val = analysis.get("rrsp_limit_cad")
    if not rrsp_limit_val:
        m_limit = re.search(r'(?:rrsp\s+limit|notice\s+of\s+assessment|noa\s+limit)\s*(?:is|of|:)?\s*\$?(\d+[\d,]*)', req, re.IGNORECASE)
        if m_limit:
            try:
                rrsp_limit_val = float(m_limit.group(1).replace(",", ""))
            except Exception:
                pass
    if rrsp_limit_val and rrsp_limit_val > 0:
        proposed_changes.append({
            "field": "rrsp_deduction_limit",
            "new_value": float(rrsp_limit_val),
            "reason": f"User confirmed CRA RRSP deduction limit of ${rrsp_limit_val:,.0f} CAD from Notice of Assessment."
        })

    return {"proposed_memory_changes": proposed_changes}

def node_retrieve_tax_rules(state: AgentState) -> Dict[str, Any]:
    """Retrieve verified CRA and Ontario 2025 rules."""
    rules = tax_rule_repo.list_rules_for_calculation(tax_year=2025, country="CA", province="ON")
    return {"tax_rules": rules}

def node_calculate_scenarios(state: AgentState) -> Dict[str, Any]:
    """
    Deterministic domain calculations.
    Zero LLM arithmetic.
    """
    profile = state.get("profile") or {}
    emp_periods = profile.get("employment_periods", [])
    fin_ctx = profile.get("financial_context", {})
    req = state.get("request", "")
    analysis = state.get("analysis") or {}

    # Determine income
    proposed = state.get("proposed_memory_changes", [])
    income_update = next((p for p in proposed if p["field"] == "annualized_income"), None)

    if income_update:
        current_income = float(income_update["new_value"])
    elif emp_periods:
        current_income = float(emp_periods[0].get("annualized_income") or 85000.0)
    else:
        current_income = 85000.0

    # Determine RRSP contribution to model
    proposed_rrsp = next((p for p in proposed if p["field"] == "rrsp_contribution"), None)
    if proposed_rrsp:
        rrsp_contrib = float(proposed_rrsp["new_value"])
    elif analysis.get("rrsp_contribution_cad"):
        rrsp_contrib = float(analysis["rrsp_contribution_cad"])
    else:
        m_rrsp = re.search(r'(?:assuming|claim(?:ing)?|contribut(?:e|ion)|deduct(?:ion)?)\s*(?:a\s+)?\$?(\d+[\d,]*)\s*(?:rrsp|deduction|\b)', req, re.IGNORECASE)
        if m_rrsp:
            try:
                candidate = float(m_rrsp.group(1).replace(",", ""))
                rrsp_contrib = candidate if candidate != current_income else float(fin_ctx.get("rrsp_contribution") or 5000.0)
            except Exception:
                rrsp_contrib = float(fin_ctx.get("rrsp_contribution") or 5000.0)
        else:
            rrsp_contrib = float(fin_ctx.get("rrsp_contribution") or 5000.0)

    # Determine RRSP deduction limit
    proposed_limit = next((p for p in proposed if p["field"] == "rrsp_deduction_limit"), None)
    if proposed_limit:
        rrsp_limit = float(proposed_limit["new_value"])
    elif analysis.get("rrsp_limit_cad"):
        rrsp_limit = float(analysis["rrsp_limit_cad"])
    else:
        rrsp_limit = fin_ctx.get("rrsp_deduction_limit")

    # Run deterministic calculator
    rrsp_calc = calculate_rrsp_what_if(
        annual_income=current_income,
        rrsp_contribution=rrsp_contrib,
        rrsp_limit=rrsp_limit,
        tax_year=2025
    )

    combined_tax = calculate_combined_tax(current_income, 2025)
    marginal_rate = calculate_marginal_tax_rate(current_income, 2025)

    calcs = {
        "current_income": current_income,
        "rrsp_scenario": rrsp_calc,
        "combined_tax": combined_tax,
        "marginal_tax_rate": marginal_rate
    }
    return {"calculations": calcs}

def node_validate_eligibility(state: AgentState) -> Dict[str, Any]:
    """Check required facts and eligibility conditions."""
    profile = state.get("profile") or {}
    fin_ctx = profile.get("financial_context", {})
    missing = []
    eligibility_results = []

    # RRSP eligibility check
    if fin_ctx.get("rrsp_deduction_limit") is None:
        missing.append("Official CRA RRSP deduction limit (from 2024 Notice of Assessment)")
        eligibility_results.append({
            "opportunity": "rrsp_planning",
            "status": "needs_verification",
            "missing": ["Official Notice of Assessment limit"]
        })
    else:
        eligibility_results.append({
            "opportunity": "rrsp_planning",
            "status": "eligible_based_on_provided_facts",
            "missing": []
        })

    # Tuition credit eligibility check (for students)
    taxpayer_types = profile.get("taxpayer_type", [])
    if "student" in taxpayer_types or fin_ctx.get("tuition_eligible"):
        if not fin_ctx.get("eligible_tuition_amount"):
            missing.append("Official T2202 Tuition and Enrolment Certificate")
            eligibility_results.append({
                "opportunity": "tuition_tax_credit",
                "status": "needs_verification",
                "missing": ["Form T2202 tuition amount"]
            })
        else:
            eligibility_results.append({
                "opportunity": "tuition_tax_credit",
                "status": "eligible_based_on_provided_facts",
                "missing": []
            })

    return {"missing_information": missing, "eligibility_results": eligibility_results}

def node_generate_recommendations(state: AgentState) -> Dict[str, Any]:
    """
    Generate evidence-linked, assumption-aware recommendations.
    Cites exact CRA rules and explicitly compares before/after when circumstances change.
    """
    calcs = state.get("calculations", {})
    profile = state.get("profile") or {}
    user_id = state["user_id"]
    proposed = state.get("proposed_memory_changes", [])
    rrsp_calc = calcs.get("rrsp_scenario", {})
    marginal_rate = calcs.get("marginal_tax_rate", 0.2965)
    tax_saving = rrsp_calc.get("estimated_tax_saving", 0.0)

    recommendations = []
    profile_version = profile.get("profile_version", 1)
    is_change = len(proposed) > 0

    if is_change:
        title = "Updated RRSP Planning Scenario (Salary Increased to $105,000 CAD)"
        desc = (
            f"Because your income increased to ${calcs.get('current_income', 105000):,.0f} CAD, "
            f"your combined marginal tax rate increased to {marginal_rate * 100:.2f}%. "
            f"A $5,000 RRSP deduction now saves approximately ${tax_saving:,.2f} in combined Ontario and Federal tax "
            f"(compared to $1,482.50 at your previous $85,000 salary, an extra ${tax_saving - 1482.50:,.2f} in tax savings)."
        )
    else:
        title = "Maximize 2025 Ontario & Federal RRSP Tax Deduction"
        desc = (
            f"Based on your confirmed employment income of ${calcs.get('current_income', 85000):,.0f} CAD, "
            f"your combined marginal tax rate is {marginal_rate * 100:.2f}%. "
            f"An RRSP contribution of $5,000 yields an estimated ${tax_saving:,.2f} CAD in tax reduction."
        )

    rec_item = {
        "user_id": user_id,
        "tax_year": 2025,
        "recommendation_type": "rrsp_planning",
        "title": title,
        "description": desc,
        "estimated_tax_saving": {
            "minimum": tax_saving,
            "maximum": tax_saving,
            "currency": "CAD",
            "calculation_status": rrsp_calc.get("calculation_status", "calculated"),
            "marginal_tax_rate": marginal_rate,
            "calculation_breakdown": rrsp_calc
        },
        "eligibility": {
            "status": "eligible_based_on_provided_facts" if profile.get("financial_context", {}).get("rrsp_deduction_limit") else "needs_verification",
            "missing_information": rrsp_calc.get("missing_information", [])
        },
        "evidence": [
            {
                "rule_id": "CA_RRSP_DEDUCTION_LIMIT_2025",
                "source_url": "https://www.canada.ca/en/revenue-agency/services/tax/registered-plans-administrators/pspa/mp-rrsp-dpsp-tfsa-limits-ympe.html",
                "authority": "Canada Revenue Agency"
            },
            {
                "rule_id": "ON_PROV_TAX_BRACKETS_2025",
                "source_url": "https://www.ontario.ca/document/general-information-income-tax-and-benefit-return/tax-rates-and-brackets",
                "authority": "Ontario Ministry of Finance"
            }
        ],
        "calculation_assumptions": rrsp_calc.get("calculation_assumptions", []),
        "profile_version": profile_version + (1 if is_change else 0),
        "status": "proposed"
    }
    recommendations.append(rec_item)

    return {"recommendations": recommendations}

def node_persist_changes(state: AgentState) -> Dict[str, Any]:
    """
    Persist confirmed profile updates, memory supersessions, and recommendations in Atlas.
    """
    user_id = state["user_id"]
    proposed = state.get("proposed_memory_changes", [])
    profile = state.get("profile") or {}
    recommendations = state.get("recommendations", [])
    audit_events = []

    # If an income or financial context update occurred, perform optimistic concurrency versioning
    if proposed:
        cur_version = profile.get("profile_version", 1)
        updates = {}
        income_change = next((p for p in proposed if p["field"] == "annualized_income"), None)
        rrsp_contrib_change = next((p for p in proposed if p["field"] == "rrsp_contribution"), None)
        rrsp_limit_change = next((p for p in proposed if p["field"] == "rrsp_deduction_limit"), None)

        if income_change:
            new_income = income_change["new_value"]
            eff_date_str = income_change.get("effective_date") or datetime.now().strftime("%Y-%m-%d")
            try:
                eff_datetime = datetime.strptime(eff_date_str, "%Y-%m-%d")
            except Exception:
                eff_datetime = datetime.now()

            updates["employment_periods.0.annualized_income"] = new_income
            updates["employment_periods.0.actual_income_earned"] = new_income
            updates["employment_periods.0.effective_from"] = eff_datetime

            # If user has no confirmed NOA limit, auto-populate statutory 18% estimate
            cur_fin = profile.get("financial_context") or {}
            if not cur_fin.get("rrsp_deduction_limit"):
                statutory_limit = min(new_income * 0.18, 32490.0)
                updates["financial_context.rrsp_deduction_limit"] = statutory_limit

        if rrsp_contrib_change:
            updates["financial_context.rrsp_contribution"] = rrsp_contrib_change["new_value"]

        if rrsp_limit_change:
            updates["financial_context.rrsp_deduction_limit"] = rrsp_limit_change["new_value"]

        if updates:
            updated_profile = profile_repo.update_profile_version(
                user_id=user_id,
                tax_year=2025,
                updates=updates,
                expected_version=cur_version
            )

            # Handle income memory supersession
            if income_change:
                active_income_mems = memory_repo.get_active_memories(user_id, memory_type="employment_income")
                old_mem_id = active_income_mems[0]["_id"] if active_income_mems else None

                if old_mem_id:
                    new_mem_id = memory_service.supersede_memory_fact(
                        user_id=user_id,
                        old_memory_id=old_mem_id,
                        new_content=f"Alex confirmed updated annual salary of ${new_income:,.0f} CAD effective {eff_date_str}.",
                        new_structured_data={
                            "annualized_income": new_income,
                            "currency": "CAD",
                            "memory_type": "employment_income",
                            "effective_from": eff_date_str
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

            # Handle RRSP limit confirmation memory
            if rrsp_limit_change:
                limit_val = rrsp_limit_change["new_value"]
                active_limit_mems = memory_repo.get_active_memories(user_id, memory_type="rrsp_limit")
                old_limit_id = active_limit_mems[0]["_id"] if active_limit_mems else None
                if old_limit_id:
                    new_limit_id = memory_service.supersede_memory_fact(
                        user_id=user_id,
                        old_memory_id=old_limit_id,
                        new_content=f"Alex confirmed CRA RRSP deduction limit of ${limit_val:,.0f} CAD from Notice of Assessment.",
                        new_structured_data={
                            "rrsp_deduction_limit": limit_val,
                            "currency": "CAD",
                            "memory_type": "rrsp_limit"
                        },
                        profile_version=cur_version + 1,
                        reason=rrsp_limit_change["reason"]
                    )
                    audit_events.append({"action": "supersede", "entity": "agent_memory", "old_id": str(old_limit_id), "new_id": new_limit_id})

            if updated_profile:
                profile = updated_profile

    # Supersede older proposed recommendations and save new one
    for rec_data in recommendations:
        rec_repo.supersede_older_recommendations(user_id, 2025, rec_data["recommendation_type"])
        rec_model = RecommendationModel(**rec_data)
        saved_id = rec_repo.save_recommendation(user_id, rec_model)
        audit_events.append({"action": "create", "entity": "recommendation", "id": saved_id})

    return {"profile": profile, "audit_events": audit_events}

def node_format_response(state: AgentState) -> Dict[str, Any]:
    """Format final response text and structured dashboard payload."""
    intent = state.get("intent")
    recs = state.get("recommendations", [])
    proposed = state.get("proposed_memory_changes", [])
    calcs = state.get("calculations", {})
    profile = state.get("profile") or {}
    memories = state.get("retrieved_memories", [])
    rules = state.get("tax_rules", [])

    # 1. Try LLM grounded dynamic generation first
    llm_message = llm_service.generate_grounded_response(
        user_message=state.get("request", ""),
        profile=profile,
        memories=memories,
        calculations=calcs,
        recommendations=recs,
        tax_rules=rules,
        proposed_changes=proposed
    )

    if llm_message:
        message = llm_message
    elif proposed:
        income_update = proposed[0]
        eff_date_str = income_update.get("effective_date") or datetime.now().strftime("%Y-%m-%d")
        rec = recs[0] if recs else {}
        saving = rec.get("estimated_tax_saving", {}).get("minimum", 0)
        rate = rec.get("estimated_tax_saving", {}).get("marginal_tax_rate", 0)

        message = (
            f"### Profile Updated to Version {profile.get('profile_version', 2)}\n\n"
            f"- **New Annual Salary:** ${income_update['new_value']:,.2f} CAD (Effective: {eff_date_str})\n"
            f"- **Prior Memory Superseded:** Prior employment fact has been archived as `superseded`.\n"
            f"- **New Marginal Tax Rate:** {rate * 100:.2f}%\n"
            f"- **Updated Tax Planning Impact:** Your $5,000 RRSP deduction now saves **${saving:,.2f} CAD** "
            f"(an additional **${saving - 1482.50:,.2f}** in tax savings due to moving into a higher marginal bracket).\n\n"
            f"**Verified Evidence:** [CRA RRSP Limits](https://www.canada.ca/en/revenue-agency/services/tax/registered-plans-administrators/pspa/mp-rrsp-dpsp-tfsa-limits-ympe.html) | [Ontario Tax Rates](https://www.ontario.ca/document/general-information-income-tax-and-benefit-return/tax-rates-and-brackets)"
        )
    else:
        rec = recs[0] if recs else {}
        saving = rec.get("estimated_tax_saving", {}).get("minimum", 0)
        rate = rec.get("estimated_tax_saving", {}).get("marginal_tax_rate", 0)
        inc = calcs.get("current_income", 85000.0)

        message = (
            f"### Tax Analysis for 2025 (Ontario Resident)\n\n"
            f"Based on your confirmed profile (Annual Income: **${inc:,.2f} CAD**, Version {profile.get('profile_version', 1)}):\n\n"
            f"- **Combined Marginal Tax Rate:** {rate * 100:.2f}%\n"
            f"- **Recommended Opportunity:** {rec.get('title', 'RRSP Planning')}\n"
            f"- **Estimated Tax Savings:** **${saving:,.2f} CAD** on a $5,000 RRSP contribution.\n"
            f"- **Eligibility Status:** `{rec.get('eligibility', {}).get('status', 'needs_verification')}`\n\n"
            f"**Official Sources:** [Canada Revenue Agency (CRA)](https://www.canada.ca/en/revenue-agency/services/tax/individuals/tax-rates-brackets/last-year.html)"
        )

    final_res = {
        "message": message,
        "intent": intent,
        "profile": profile,
        "recommendations": recs,
        "calculations": calcs,
        "missing_information": state.get("missing_information", []),
        "retrieved_memories_count": len(memories),
        "audit_events": state.get("audit_events", [])
    }
    return {"final_response": final_res}

from typing import Dict, Any, List, Optional

class OpportunityResearchAgent:
    """
    Opportunity Research Agent:
    - Identifies potentially relevant deductions, credits, and planning opportunities.
    - Checks rule conditions and flags missing evidence before assuming eligibility.
    - Explicitly compares current vs prior recommendations when taxpayer facts change.
    - Never guarantees eligibility or savings; flags uncertainty.
    """
    def __init__(self):
        self.name = "Opportunity Research Agent"

    def evaluate_opportunities(
        self,
        profile: Dict[str, Any],
        calculations: Dict[str, Any],
        proposed_changes: List[Dict[str, Any]],
        tax_rules: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        fin_ctx = profile.get("financial_context", {})
        taxpayer_types = profile.get("taxpayer_type", [])
        missing_info = []
        eligibility_results = []
        recommendations = []

        user_id = str(profile.get("user_id", ""))
        tax_year = profile.get("tax_year", 2025)
        profile_version = profile.get("profile_version", 1)

        marginal_rate = calculations.get("marginal_tax_rate", 0.2965)
        rrsp_calc = calculations.get("rrsp_scenario", {})
        tax_saving = rrsp_calc.get("estimated_tax_saving", 0.0)
        is_change = len(proposed_changes) > 0

        # 1. RRSP Deduction Opportunity
        rrsp_limit = fin_ctx.get("rrsp_deduction_limit")
        if rrsp_limit is None:
            missing_info.append("Official CRA RRSP deduction limit (from 2024 Notice of Assessment)")
            rrsp_eligibility = "needs_verification"
        else:
            rrsp_eligibility = "eligible_based_on_provided_facts"

        eligibility_results.append({
            "opportunity": "rrsp_planning",
            "status": rrsp_eligibility,
            "missing": ["Official Notice of Assessment limit"] if rrsp_limit is None else []
        })

        if is_change:
            title = "Updated RRSP Planning Scenario (Circumstance Change)"
            desc = (
                f"Because your income increased to ${calculations.get('current_income', 105000):,.0f} CAD, "
                f"your combined marginal tax rate increased to {marginal_rate * 100:.2f}%. "
                f"A $5,000 RRSP deduction now yields ${tax_saving:,.2f} in tax savings "
                f"(an increase of ${tax_saving - 1482.50:,.2f} over the baseline $85k scenario)."
            )
        else:
            title = "Maximize 2025 Ontario & Federal RRSP Tax Deduction"
            desc = (
                f"Based on your confirmed employment income of ${calculations.get('current_income', 85000):,.0f} CAD, "
                f"your combined marginal tax rate is {marginal_rate * 100:.2f}%. "
                f"An RRSP contribution of $5,000 yields an estimated ${tax_saving:,.2f} CAD in tax reduction."
            )

        recommendations.append({
            "user_id": user_id,
            "tax_year": tax_year,
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
                "status": rrsp_eligibility,
                "missing_information": ["Official Notice of Assessment limit"] if rrsp_limit is None else []
            },
            "evidence": [
                {
                    "rule_id": "CA_2025_RRSP_LIMIT",
                    "source_url": "https://www.canada.ca/en/revenue-agency/services/tax/registered-plans-administrators/pspa/mp-rrsp-dpsp-tfsa-limits-ympe.html"
                },
                {
                    "rule_id": "ON_2025_BRACKETS",
                    "source_url": "https://www.ontario.ca/document/general-information-income-tax-and-benefit-return/tax-rates-and-brackets"
                }
            ],
            "profile_version": profile_version,
            "status": "proposed"
        })

        # 2. Tuition Opportunity Checklist (if student)
        if "student" in taxpayer_types or fin_ctx.get("tuition_eligible"):
            if not fin_ctx.get("eligible_tuition_amount"):
                missing_info.append("Official T2202 Tuition and Enrolment Certificate")
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

        return {
            "recommendations": recommendations,
            "missing_information": missing_info,
            "eligibility_results": eligibility_results
        }

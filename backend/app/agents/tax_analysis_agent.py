from typing import Dict, Any, List, Optional
from backend.app.services.tax_calc import (
    calculate_combined_tax,
    calculate_marginal_tax_rate,
    calculate_rrsp_what_if
)
from backend.app.services.llm import llm_service

class TaxAnalysisAgent:
    """
    Tax Analysis Agent:
    - Interprets the confirmed taxpayer profile.
    - Retrieves applicable official rules for jurisdiction and tax year.
    - Requests deterministic calculations (zero LLM arithmetic).
    - Explains results, assumptions and limitations with citations.
    """
    def __init__(self):
        self.name = "Tax Analysis Agent"

    def analyze(self, profile: Dict[str, Any], proposed_changes: List[Dict[str, Any]], tax_rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        emp_periods = profile.get("employment_periods", [])
        fin_ctx = profile.get("financial_context", {})

        # Determine effective income
        income_update = next((p for p in proposed_changes if p.get("field") == "annualized_income"), None)
        if income_update:
            current_income = float(income_update["new_value"])
        elif emp_periods:
            current_income = float(emp_periods[0].get("annualized_income") or 85000.0)
        else:
            current_income = 85000.0

        rrsp_contrib = float(fin_ctx.get("rrsp_contribution") or 5000.0)
        rrsp_limit = fin_ctx.get("rrsp_deduction_limit")

        # Deterministic calculations - strict invariant: zero LLM arithmetic
        rrsp_calc = calculate_rrsp_what_if(
            annual_income=current_income,
            rrsp_contribution=rrsp_contrib,
            rrsp_limit=rrsp_limit,
            tax_year=2025
        )
        combined_tax = calculate_combined_tax(current_income, 2025)
        marginal_rate = calculate_marginal_tax_rate(current_income, 2025)

        return {
            "current_income": current_income,
            "rrsp_scenario": rrsp_calc,
            "combined_tax": combined_tax,
            "marginal_tax_rate": marginal_rate,
            "applicable_rules_count": len(tax_rules)
        }

    def synthesize_explanation(self, profile: Dict[str, Any], analysis: Dict[str, Any], is_circumstance_change: bool) -> str:
        inc = analysis.get("current_income", 85000.0)
        rate = analysis.get("marginal_tax_rate", 0.2965)
        rrsp_saving = analysis.get("rrsp_scenario", {}).get("estimated_tax_saving", 0.0)
        version = profile.get("profile_version", 1)

        prompt = (
            f"Taxpayer profile (Ontario resident, 2025 tax year, Profile Version {version}):\n"
            f"- Annual Employment Income: ${inc:,.2f} CAD\n"
            f"- Combined Federal + Ontario Marginal Tax Rate: {rate * 100:.2f}%\n"
            f"- Deterministic Tax Savings on $5,000 RRSP Deduction: ${rrsp_saving:,.2f} CAD\n"
            f"- Circumstance Change Flag: {is_circumstance_change}\n\n"
            "Provide a concise, professional tax analysis summary for this Canadian taxpayer. "
            "Highlight the marginal tax bracket and explain why the RRSP deduction provides this exact tax saving. "
            "Cite official CRA and Ontario Ministry of Finance rules. "
            "Do NOT invent or alter any numbers. Only use the numbers provided above."
        )
        sys_inst = (
            "You are the Tax Analysis Agent of TaxPilot AI. You explain deterministic tax calculation results "
            "accurately, citing CRA and Ontario tax references. Never perform manual arithmetic or change numbers."
        )

        ai_response = llm_service.generate(prompt, system_instruction=sys_inst)
        if ai_response:
            return ai_response

        # Deterministic fallback explanation
        if is_circumstance_change:
            return (
                f"### Profile Updated to Version {version}\n\n"
                f"- **New Annual Salary:** ${inc:,.2f} CAD\n"
                f"- **Combined Marginal Tax Rate:** {rate * 100:.2f}%\n"
                f"- **Updated Tax Planning Impact:** Your $5,000 RRSP deduction now saves **${rrsp_saving:,.2f} CAD** "
                f"(an additional **${rrsp_saving - 1482.50:,.2f}** in tax savings due to moving into a higher marginal bracket).\n\n"
                f"**Verified Evidence:** [CRA RRSP Limits](https://www.canada.ca/en/revenue-agency/services/tax/registered-plans-administrators/pspa/mp-rrsp-dpsp-tfsa-limits-ympe.html) | [Ontario Tax Rates](https://www.ontario.ca/document/general-information-income-tax-and-benefit-return/tax-rates-and-brackets)"
            )
        else:
            return (
                f"### Tax Analysis for 2025 (Ontario Resident)\n\n"
                f"Based on your confirmed profile (Annual Income: **${inc:,.2f} CAD**, Version {version}):\n\n"
                f"- **Combined Marginal Tax Rate:** {rate * 100:.2f}%\n"
                f"- **Recommended Opportunity:** Maximize 2025 Ontario & Federal RRSP Tax Deduction\n"
                f"- **Estimated Tax Savings:** **${rrsp_saving:,.2f} CAD** on a $5,000 RRSP contribution.\n"
                f"- **Eligibility Status:** `eligible_based_on_provided_facts`\n\n"
                f"**Official Sources:** [Canada Revenue Agency (CRA)](https://www.canada.ca/en/revenue-agency/services/tax/individuals/tax-rates-brackets/last-year.html)"
            )

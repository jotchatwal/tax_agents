"""
Deterministic Canadian (Federal & Ontario) Tax Calculation Engine.
Strict Invariant: ZERO LLM ARITHMETIC. All tax brackets, marginal rates,
and RRSP deduction what-if savings are calculated deterministically
based on verified CRA and Ontario Ministry of Finance rules.
"""

from typing import Dict, Any, List, Optional, Tuple

# Official Verified 2025 Federal Brackets & Rates (CRA)
FED_BRACKETS_2025 = [
    (0.0, 57375.0, 0.1500),
    (57375.0, 114750.0, 0.2050),
    (114750.0, 177882.0, 0.2600),
    (177882.0, 253414.0, 0.2900),
    (253414.0, float("inf"), 0.3300),
]
FED_BPA_2025 = 16129.0  # Federal Basic Personal Amount

# Official Verified 2025 Ontario Brackets & Rates (Ontario Ministry of Finance)
ON_BRACKETS_2025 = [
    (0.0, 52875.0, 0.0505),
    (52875.0, 105754.0, 0.0915),
    (105754.0, 150000.0, 0.1116),
    (150000.0, 220000.0, 0.1216),
    (220000.0, float("inf"), 0.1316),
]
ON_BPA_2025 = 12692.0  # Ontario Basic Personal Amount
ON_SURTAX_1_THRESHOLD = 5554.0
ON_SURTAX_1_RATE = 0.20
ON_SURTAX_2_THRESHOLD = 7108.0
ON_SURTAX_2_RATE = 0.36

# Maximum RRSP Statutory Deduction Limit for 2025
RRSP_STATUTORY_MAX_2025 = 32490.0
RRSP_EARNED_INCOME_RATE = 0.18

def calculate_bracket_tax(income: float, brackets: List[Tuple[float, float, float]]) -> Tuple[float, List[Dict[str, Any]]]:
    """Calculate progressive tax across tiered brackets."""
    total_tax = 0.0
    breakdown = []
    if income <= 0:
        return 0.0, breakdown

    for lower, upper, rate in brackets:
        if income > lower:
            taxable_in_bracket = min(income, upper) - lower
            bracket_tax = taxable_in_bracket * rate
            total_tax += bracket_tax
            breakdown.append({
                "bracket_range": f"${lower:,.0f} - {('$' + f'{upper:,.0f}') if upper != float('inf') else 'above'}",
                "taxable_amount": round(taxable_in_bracket, 2),
                "rate": rate,
                "bracket_tax": round(bracket_tax, 2)
            })
        else:
            break
    return total_tax, breakdown

def calculate_federal_tax(taxable_income: float, tax_year: int = 2025) -> Dict[str, Any]:
    """Calculate gross and net federal tax for a given taxable income."""
    if taxable_income <= 0:
        return {"gross_tax": 0.0, "non_refundable_credits": 0.0, "net_tax": 0.0, "breakdown": []}

    gross_tax, breakdown = calculate_bracket_tax(taxable_income, FED_BRACKETS_2025)
    # Federal basic personal amount non-refundable tax credit (15% of BPA)
    bpa_credit = min(taxable_income, FED_BPA_2025) * 0.1500
    net_tax = max(0.0, gross_tax - bpa_credit)

    return {
        "gross_tax": round(gross_tax, 2),
        "non_refundable_credits": round(bpa_credit, 2),
        "net_tax": round(net_tax, 2),
        "breakdown": breakdown
    }

def calculate_ontario_tax(taxable_income: float, tax_year: int = 2025) -> Dict[str, Any]:
    """Calculate gross provincial tax, basic credit, surtaxes, and net Ontario tax."""
    if taxable_income <= 0:
        return {"gross_tax": 0.0, "credits": 0.0, "surtax": 0.0, "net_tax": 0.0, "breakdown": []}

    gross_tax, breakdown = calculate_bracket_tax(taxable_income, ON_BRACKETS_2025)
    # Ontario basic personal credit (5.05% of BPA)
    bpa_credit = min(taxable_income, ON_BPA_2025) * 0.0505
    basic_ontario_tax = max(0.0, gross_tax - bpa_credit)

    # Ontario Surtax calculation
    surtax = 0.0
    if basic_ontario_tax > ON_SURTAX_1_THRESHOLD:
        surtax += (basic_ontario_tax - ON_SURTAX_1_THRESHOLD) * ON_SURTAX_1_RATE
    if basic_ontario_tax > ON_SURTAX_2_THRESHOLD:
        surtax += (basic_ontario_tax - ON_SURTAX_2_THRESHOLD) * ON_SURTAX_2_RATE

    net_tax = basic_ontario_tax + surtax

    return {
        "gross_tax": round(gross_tax, 2),
        "basic_credit": round(bpa_credit, 2),
        "basic_tax_after_credit": round(basic_ontario_tax, 2),
        "surtax": round(surtax, 2),
        "net_tax": round(net_tax, 2),
        "breakdown": breakdown
    }

def calculate_combined_tax(taxable_income: float, tax_year: int = 2025) -> Dict[str, Any]:
    """Calculate combined Federal and Ontario provincial personal income tax."""
    fed = calculate_federal_tax(taxable_income, tax_year)
    ont = calculate_ontario_tax(taxable_income, tax_year)
    total_net = fed["net_tax"] + ont["net_tax"]
    effective_rate = (total_net / taxable_income) if taxable_income > 0 else 0.0

    return {
        "taxable_income": round(taxable_income, 2),
        "federal_tax": fed,
        "ontario_tax": ont,
        "total_tax": round(total_net, 2),
        "effective_tax_rate": round(effective_rate, 4)
    }

def calculate_marginal_tax_rate(taxable_income: float, tax_year: int = 2025) -> float:
    """
    Deterministically computes the marginal tax rate by calculating the tax
    on the next dollar of income.
    """
    if taxable_income <= 0:
        return 0.2005  # Lowest combined bracket (15% + 5.05%)
    delta = 100.0
    tax_base = calculate_combined_tax(taxable_income, tax_year)["total_tax"]
    tax_plus = calculate_combined_tax(taxable_income + delta, tax_year)["total_tax"]
    marginal_rate = (tax_plus - tax_base) / delta
    return round(marginal_rate, 4)

def calculate_rrsp_what_if(
    annual_income: float,
    rrsp_contribution: float,
    rrsp_limit: Optional[float] = None,
    tax_year: int = 2025
) -> Dict[str, Any]:
    """
    Deterministic RRSP scenario calculation.
    Computes exact tax before and after RRSP deduction, marginal tax savings,
    and flags any overcontribution or missing official limit facts.
    """
    if annual_income <= 0 or rrsp_contribution <= 0:
        return {
            "calculation_status": "not_calculated",
            "reason": "Income and contribution must be greater than zero.",
            "estimated_tax_saving": None,
            "marginal_tax_rate": None
        }

    # Verify if RRSP limit is provided
    missing_information = []
    calculation_status = "calculated"
    effective_deduction = rrsp_contribution

    if rrsp_limit is None:
        missing_information.append("Official CRA RRSP deduction limit from Notice of Assessment")
        # In tax planning, statutory estimate is 18% of earned income up to annual cap
        estimated_room = min(annual_income * RRSP_EARNED_INCOME_RATE, RRSP_STATUTORY_MAX_2025)
        calculation_status = "needs_verification"
        assumptions = [
            f"Assumed estimated RRSP room of ${estimated_room:,.0f} (18% of income) pending official CRA Notice of Assessment."
        ]
        effective_deduction = min(rrsp_contribution, estimated_room)
    else:
        assumptions = [
            f"Verified against user-provided CRA deduction limit of ${rrsp_limit:,.0f}."
        ]
        if rrsp_contribution > rrsp_limit:
            calculation_status = "needs_verification"
            over_amount = rrsp_contribution - rrsp_limit
            assumptions.append(
                f"WARNING: Proposed contribution (${rrsp_contribution:,.0f}) exceeds deduction limit (${rrsp_limit:,.0f}) by ${over_amount:,.0f}. CRA imposes 1% monthly penalty tax on excess over $2,000."
            )
            effective_deduction = rrsp_limit

    # Deterministic computation
    baseline = calculate_combined_tax(annual_income, tax_year)
    new_taxable_income = max(0.0, annual_income - effective_deduction)
    reduced = calculate_combined_tax(new_taxable_income, tax_year)

    tax_saving = max(0.0, baseline["total_tax"] - reduced["total_tax"])
    marginal_rate = calculate_marginal_tax_rate(annual_income, tax_year)

    return {
        "calculation_status": calculation_status,
        "tax_year": tax_year,
        "original_income": round(annual_income, 2),
        "deduction_claimed": round(effective_deduction, 2),
        "new_taxable_income": round(new_taxable_income, 2),
        "baseline_tax": baseline["total_tax"],
        "reduced_tax": reduced["total_tax"],
        "estimated_tax_saving": round(tax_saving, 2),
        "marginal_tax_rate": marginal_rate,
        "calculation_assumptions": assumptions,
        "missing_information": missing_information,
        "source_reference": {
            "rule_id": "CA_RRSP_DEDUCTION_LIMIT_2025",
            "source_url": "https://www.canada.ca/en/revenue-agency/services/tax/registered-plans-administrators/pspa/mp-rrsp-dpsp-tfsa-limits-ympe.html",
            "authority": "Canada Revenue Agency"
        }
    }

import unittest
from backend.app.services.tax_calc import (
    calculate_federal_tax,
    calculate_ontario_tax,
    calculate_combined_tax,
    calculate_marginal_tax_rate,
    calculate_rrsp_what_if
)

class TestDeterministicTaxCalculator(unittest.TestCase):

    def test_zero_and_negative_income(self):
        res_zero = calculate_combined_tax(0.0)
        self.assertEqual(res_zero["total_tax"], 0.0)
        self.assertEqual(res_zero["effective_tax_rate"], 0.0)

        res_neg = calculate_combined_tax(-1000.0)
        self.assertEqual(res_neg["total_tax"], 0.0)

    def test_federal_tax_brackets(self):
        # At $50,000 (entirely in first 15% bracket)
        # Gross = 50,000 * 0.15 = 7,500. Credit = 16,129 * 0.15 = 2,419.35
        # Net = 7,500 - 2,419.35 = 5,080.65
        fed = calculate_federal_tax(50000.0)
        self.assertAlmostEqual(fed["gross_tax"], 7500.0, places=2)
        self.assertAlmostEqual(fed["non_refundable_credits"], 2419.35, places=2)
        self.assertAlmostEqual(fed["net_tax"], 5080.65, places=2)

    def test_marginal_rate_increase_with_income(self):
        # Marginal rate at $85,000 should be around 29.65%
        rate_85k = calculate_marginal_tax_rate(85000.0)
        self.assertGreaterEqual(rate_85k, 0.29)
        self.assertLessEqual(rate_85k, 0.32)

        # Marginal rate at $105,000 is higher than $85,000
        rate_105k = calculate_marginal_tax_rate(105000.0)
        self.assertGreater(rate_105k, rate_85k)

        # At $110,000 (past the $105,754 Ontario bracket threshold), rate rises further
        rate_110k = calculate_marginal_tax_rate(110000.0)
        self.assertGreater(rate_110k, rate_105k)
        self.assertGreaterEqual(rate_110k, 0.35)

    def test_rrsp_what_if_demo_thesis(self):
        # Core Thesis: The same $5,000 RRSP contribution yields GREATER tax savings
        # when salary rises from $85k to $105k!
        res_85k = calculate_rrsp_what_if(
            annual_income=85000.0,
            rrsp_contribution=5000.0,
            rrsp_limit=18000.0
        )
        self.assertEqual(res_85k["calculation_status"], "calculated")
        saving_85k = res_85k["estimated_tax_saving"]

        res_105k = calculate_rrsp_what_if(
            annual_income=105000.0,
            rrsp_contribution=5000.0,
            rrsp_limit=18000.0
        )
        self.assertEqual(res_105k["calculation_status"], "calculated")
        saving_105k = res_105k["estimated_tax_saving"]

        # Mathematical verification of thesis:
        self.assertGreater(saving_105k, saving_85k)
        print(f"\n[Thesis Verified] RRSP $5k Tax Saving at $85k: ${saving_85k:,.2f} | at $105k: ${saving_105k:,.2f} (Diff: +${saving_105k - saving_85k:,.2f})")

    def test_rrsp_missing_limit_guardrail(self):
        # When RRSP limit is unknown, status MUST be needs_verification
        res = calculate_rrsp_what_if(
            annual_income=85000.0,
            rrsp_contribution=5000.0,
            rrsp_limit=None
        )
        self.assertEqual(res["calculation_status"], "needs_verification")
        self.assertTrue(any("Notice of Assessment" in item for item in res["missing_information"]))

    def test_rrsp_overcontribution_warning(self):
        # Contribution $15k exceeds limit of $10k
        res = calculate_rrsp_what_if(
            annual_income=85000.0,
            rrsp_contribution=15000.0,
            rrsp_limit=10000.0
        )
        self.assertEqual(res["calculation_status"], "needs_verification")
        self.assertTrue(any("WARNING" in item for item in res["calculation_assumptions"]))

if __name__ == "__main__":
    unittest.main()

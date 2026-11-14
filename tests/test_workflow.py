import unittest
from bson import ObjectId
from backend.app.db.mongo import get_db
from backend.app.db.repositories import (
    UserRepository,
    ProfileRepository,
    MemoryRepository,
    TaxRuleRepository,
    AuditRepository
)
from backend.app.models.user import UserModel
from backend.app.models.profile import TaxProfileModel, EmploymentPeriod, FinancialContext, Jurisdiction
from backend.app.models.memory import AgentMemoryModel, MemorySource, MemoryGovernance
from backend.app.graph.orchestrator import run_taxpilot_workflow

class TestEndToEndWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = get_db()
        cls.user_repo = UserRepository(cls.db)
        cls.profile_repo = ProfileRepository(cls.db)
        cls.memory_repo = MemoryRepository(cls.db)
        cls.audit_repo = AuditRepository(cls.db)

        # Create isolated demo user for this run
        cls.user_email = f"alex_workflow_{ObjectId()}@example.com"
        cls.user_id = cls.user_repo.create_user(UserModel(
            email=cls.user_email,
            display_name="Alex Mercer",
            role="taxpayer"
        ))

        # Seed initial Profile (v1: $85,000)
        cls.profile_repo.create_profile(cls.user_id, TaxProfileModel(
            user_id=cls.user_id,
            jurisdiction=Jurisdiction(country="CA", province="ON"),
            tax_year=2025,
            employment_periods=[
                EmploymentPeriod(
                    employer_label="TechCorp Canada",
                    annualized_income=85000.0,
                    actual_income_earned=85000.0,
                    source_status="user_confirmed"
                )
            ],
            financial_context=FinancialContext(
                rrsp_contribution=5000.0,
                rrsp_deduction_limit=18000.0,
                tfsa_status="active"
            ),
            profile_version=1
        ))

        # Seed initial active memory for $85,000
        cls.memory_repo.create_memory(cls.user_id, AgentMemoryModel(
            user_id=cls.user_id,
            memory_type="employment_income",
            content="Alex confirmed annual employment income of $85,000 CAD at TechCorp Canada for tax year 2025.",
            structured_data={"annualized_income": 85000.0, "currency": "CAD"},
            source=MemorySource(type="onboarding", profile_version=1),
            governance=MemoryGovernance(status="active", verification_status="user_confirmed")
        ))

    def test_session_1_initial_recommendation(self):
        """Session 1: Initial query produces baseline recommendation from $85k profile."""
        res = run_taxpilot_workflow(
            user_id=self.user_id,
            request="What tax-planning opportunities should I review based on my current profile?",
            session_id="session_1"
        )
        self.assertIn("message", res)
        self.assertEqual(res["intent"], "question")
        self.assertEqual(len(res["recommendations"]), 1)

        rec = res["recommendations"][0]
        self.assertEqual(rec["recommendation_type"], "rrsp_planning")
        saving = rec["estimated_tax_saving"]["minimum"]
        self.assertAlmostEqual(saving, 1482.50, delta=1.0)
        print(f"\n[Session 1 Success] Initial $85k Profile Savings: ${saving:,.2f}")

    def test_session_2_changed_income_workflow(self):
        """
        Session 2: Material change (salary rises to $105,000).
        Profile increments to v2, memory is superseded, and savings increase deterministically.
        """
        res = run_taxpilot_workflow(
            user_id=self.user_id,
            request="I changed jobs and my annual salary is now 105000 CAD.",
            session_id="session_2"
        )
        self.assertIn("message", res)
        self.assertEqual(res["intent"], "profile_update")

        # 1. Profile version incremented to 2 in Atlas
        updated_profile = self.profile_repo.get_current_profile(self.user_id, 2025)
        self.assertEqual(updated_profile["profile_version"], 2)
        self.assertEqual(updated_profile["employment_periods"][0]["annualized_income"], 105000.0)

        # 2. Prior memory superseded in Atlas
        all_income_mems = self.memory_repo.get_all_user_memories(self.user_id)
        superseded_mems = [m for m in all_income_mems if m["governance"]["status"] == "superseded"]
        active_mems = [m for m in all_income_mems if m["governance"]["status"] == "active"]

        self.assertGreaterEqual(len(superseded_mems), 1)
        self.assertGreaterEqual(len(active_mems), 1)
        self.assertIn("105,000", active_mems[0]["content"])

        # 3. Deterministic recalculation: Savings increase to $1,574.00
        rec = res["recommendations"][0]
        saving_105k = rec["estimated_tax_saving"]["minimum"]
        self.assertAlmostEqual(saving_105k, 1574.00, delta=1.0)
        self.assertGreater(saving_105k, 1482.50)

        # 4. Audit trail recorded in Atlas
        audit_logs = self.audit_repo.get_user_audit_logs(self.user_id)
        self.assertTrue(any(l["event_type"] == "memory_superseded" for l in audit_logs))

        print(f"\n[Session 2 Success] Updated $105k Profile Savings: ${saving_105k:,.2f} (Profile v2, Memory Superseded!)")

if __name__ == "__main__":
    unittest.main()

import unittest
from bson import ObjectId
from backend.app.db.mongo import get_db
from backend.app.db.repositories import (
    UserRepository,
    ProfileRepository,
    MemoryRepository,
    RecommendationRepository,
    AuditRepository
)
from backend.app.models.user import UserModel
from backend.app.models.profile import TaxProfileModel, Jurisdiction, EmploymentPeriod
from backend.app.models.memory import AgentMemoryModel, MemorySource, MemoryGovernance

class TestTenantIsolationAndMemoryGovernance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = get_db()
        cls.user_repo = UserRepository(cls.db)
        cls.profile_repo = ProfileRepository(cls.db)
        cls.memory_repo = MemoryRepository(cls.db)
        cls.rec_repo = RecommendationRepository(cls.db)
        cls.audit_repo = AuditRepository(cls.db)

        # Setup isolated demo users
        cls.user_a_email = f"alpha_{ObjectId()}@example.com"
        cls.user_b_email = f"beta_{ObjectId()}@example.com"

        cls.user_a_id = cls.user_repo.create_user(UserModel(
            email=cls.user_a_email,
            display_name="User Alpha",
            role="taxpayer"
        ))
        cls.user_b_id = cls.user_repo.create_user(UserModel(
            email=cls.user_b_email,
            display_name="User Beta",
            role="taxpayer"
        ))

    def test_01_profile_cross_user_isolation(self):
        # User A creates a profile
        self.profile_repo.create_profile(self.user_a_id, TaxProfileModel(
            user_id=self.user_a_id,
            jurisdiction=Jurisdiction(country="CA", province="ON"),
            tax_year=2025,
            employment_periods=[
                EmploymentPeriod(employer_label="Alpha Corp", annualized_income=90000.0)
            ],
            profile_version=1
        ))

        # User A can read their own profile
        profile_a = self.profile_repo.get_current_profile(self.user_a_id, 2025)
        self.assertIsNotNone(profile_a)
        self.assertEqual(profile_a["employment_periods"][0]["annualized_income"], 90000.0)

        # User B CANNOT read User A's profile (server-side tenant isolation)
        profile_b_attempt = self.profile_repo.get_current_profile(self.user_b_id, 2025)
        self.assertIsNone(profile_b_attempt)

    def test_02_memory_cross_user_isolation(self):
        # User A creates a confidential memory
        mem_a_id = self.memory_repo.create_memory(self.user_a_id, AgentMemoryModel(
            user_id=self.user_a_id,
            memory_type="financial_target",
            content="User A confidential target: invest $10k in RRSP",
            source=MemorySource(type="user_statement", profile_version=1),
            governance=MemoryGovernance(status="active")
        ))

        # User A can retrieve it
        mem_a = self.memory_repo.get_memory_by_id(self.user_a_id, mem_a_id)
        self.assertIsNotNone(mem_a)
        self.assertIn("invest $10k", mem_a["content"])

        # User B CANNOT read User A's memory even with the exact memory ID
        mem_b_attempt = self.memory_repo.get_memory_by_id(self.user_b_id, mem_a_id)
        self.assertIsNone(mem_b_attempt)

        # User B CANNOT update or supersede User A's memory
        tamper_result = self.memory_repo.supersede_memory(self.user_b_id, mem_a_id, ObjectId())
        self.assertFalse(tamper_result)

        # User B CANNOT delete User A's memory
        delete_result = self.memory_repo.delete_memory(self.user_b_id, mem_a_id, deletion_reason="Malicious deletion attempt")
        self.assertFalse(delete_result)

        # Verify User A's memory remains intact and active
        intact_mem = self.memory_repo.get_memory_by_id(self.user_a_id, mem_a_id)
        self.assertEqual(intact_mem["governance"]["status"], "active")
        self.assertEqual(intact_mem["content"], "User A confidential target: invest $10k in RRSP")

    def test_03_memory_lifecycle_supersession_and_deletion(self):
        # 1. Create original memory
        orig_id = self.memory_repo.create_memory(self.user_a_id, AgentMemoryModel(
            user_id=self.user_a_id,
            memory_type="salary",
            content="Alex earns $85,000",
            governance=MemoryGovernance(status="active")
        ))

        # 2. Supersede with new memory ($105,000)
        new_id = self.memory_repo.create_memory(self.user_a_id, AgentMemoryModel(
            user_id=self.user_a_id,
            memory_type="salary",
            content="Alex earns $105,000",
            governance=MemoryGovernance(status="active", supersedes_memory_id=orig_id)
        ))

        superseded_ok = self.memory_repo.supersede_memory(self.user_a_id, orig_id, new_id)
        self.assertTrue(superseded_ok)

        # Check original memory is superseded and points to replacement
        orig_doc = self.memory_repo.get_memory_by_id(self.user_a_id, orig_id)
        self.assertEqual(orig_doc["governance"]["status"], "superseded")
        self.assertEqual(str(orig_doc["governance"]["superseded_by_memory_id"]), str(new_id))

        # Active memory query only returns new memory
        active_mems = self.memory_repo.get_active_memories(self.user_a_id, "salary")
        self.assertEqual(len(active_mems), 1)
        self.assertEqual(str(active_mems[0]["_id"]), str(new_id))

        # 3. Test deletion of new memory
        del_ok = self.memory_repo.delete_memory(self.user_a_id, new_id, deletion_reason="User requested erasure")
        self.assertTrue(del_ok)

        # Content wiped, embedding wiped, marked deleted
        del_doc = self.memory_repo.get_memory_by_id(self.user_a_id, new_id)
        self.assertEqual(del_doc["governance"]["status"], "deleted")
        self.assertEqual(del_doc["content"], "[DELETED BY USER]")
        self.assertIsNone(del_doc.get("embedding"))

    def test_04_optimistic_concurrency_profile_versioning(self):
        # Current version is 1
        profile = self.profile_repo.get_current_profile(self.user_a_id, 2025)
        self.assertEqual(profile["profile_version"], 1)

        # Stale write attempt (expecting version 99) fails
        stale_update = self.profile_repo.update_profile_version(
            self.user_a_id, 2025, {"financial_context.rrsp_contribution": 7000.0}, expected_version=99
        )
        self.assertIsNone(stale_update)

        # Correct write (expecting version 1) succeeds and bumps to version 2
        success_update = self.profile_repo.update_profile_version(
            self.user_a_id, 2025, {"financial_context.rrsp_contribution": 7000.0}, expected_version=1
        )
        self.assertIsNotNone(success_update)
        self.assertEqual(success_update["profile_version"], 2)
        self.assertEqual(success_update["financial_context"]["rrsp_contribution"], 7000.0)

    @classmethod
    def tearDownClass(cls):
        for uid_str in [getattr(cls, "user_a_id", None), getattr(cls, "user_b_id", None)]:
            if uid_str:
                uid = ObjectId(uid_str)
                cls.db["tax_profiles"].delete_many({"user_id": uid})
                cls.db["agent_memories"].delete_many({"user_id": uid})
                cls.db["audit_logs"].delete_many({"user_id": uid})
                cls.db["recommendations"].delete_many({"user_id": uid})
                cls.db["users"].delete_one({"_id": uid})

if __name__ == "__main__":
    unittest.main()

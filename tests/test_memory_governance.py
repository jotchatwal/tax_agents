import unittest
from bson import ObjectId
from backend.app.db.mongo import get_db
from backend.app.db.repositories import UserRepository, MemoryRepository, AuditRepository
from backend.app.models.user import UserModel
from backend.app.services.memory_service import MemoryGovernanceService, embedding_service

class TestMemoryGovernanceService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = get_db()
        cls.user_repo = UserRepository(cls.db)
        cls.memory_repo = MemoryRepository(cls.db)
        cls.audit_repo = AuditRepository(cls.db)
        cls.mem_service = MemoryGovernanceService(cls.memory_repo, cls.audit_repo)

        # Create isolated test user
        cls.user_email = f"memory_tester_{ObjectId()}@example.com"
        cls.user_id = cls.user_repo.create_user(UserModel(
            email=cls.user_email,
            display_name="Memory Tester",
            role="taxpayer"
        ))

    def test_embedding_dimensions(self):
        vec = embedding_service.embed_text("Annual salary of 105,000 CAD in Ontario")
        self.assertEqual(len(vec), 384)
        self.assertAlmostEqual(sum(x**2 for x in vec)**0.5, 1.0, places=3)

    def test_propose_and_confirm_memory(self):
        # 1. Propose memory
        prop = self.mem_service.propose_memory(
            user_id=self.user_id,
            memory_type="employment_income",
            content="User stated salary is $85,000 CAD",
            structured_data={"annualized_income": 85000.0, "currency": "CAD"},
            raw_statement="My salary is $85k",
            profile_version=1,
            auto_confirm=False
        )
        mem_id = prop["memory_id"]
        self.assertEqual(prop["status"], "pending_confirmation")
        self.assertEqual(prop["verification_status"], "unconfirmed")

        # Verify not returned in active memories
        active = self.mem_service.retrieve_active_memories(self.user_id, memory_type="employment_income")
        self.assertFalse(any(str(m["_id"]) == str(mem_id) for m in active))

        # 2. Confirm memory
        confirmed = self.mem_service.confirm_memory(self.user_id, mem_id)
        self.assertTrue(confirmed)

        # Verify now active with embedding
        updated_doc = self.memory_repo.get_memory_by_id(self.user_id, mem_id)
        self.assertEqual(updated_doc["governance"]["status"], "active")
        self.assertEqual(updated_doc["governance"]["verification_status"], "user_confirmed")
        self.assertIsNotNone(updated_doc["embedding"])
        self.assertEqual(len(updated_doc["embedding"]), 384)

    def test_supersede_material_fact(self):
        # First active memory: $85,000
        initial_prop = self.mem_service.propose_memory(
            user_id=self.user_id,
            memory_type="employment_income",
            content="Confirmed salary: $85,000 CAD",
            structured_data={"annualized_income": 85000.0},
            raw_statement="Salary is 85000",
            profile_version=1,
            auto_confirm=True
        )
        old_mem_id = initial_prop["memory_id"]

        # User reports salary increased to $105,000
        new_mem_id = self.mem_service.supersede_memory_fact(
            user_id=self.user_id,
            old_memory_id=old_mem_id,
            new_content="Promoted to Senior Engineer with new annualized salary of $105,000 CAD",
            new_structured_data={"annualized_income": 105000.0, "memory_type": "employment_income"},
            profile_version=2,
            reason="User confirmed job promotion and salary increase to $105k"
        )
        self.assertIsNotNone(new_mem_id)

        # Old memory is superseded
        old_doc = self.memory_repo.get_memory_by_id(self.user_id, old_mem_id)
        self.assertEqual(old_doc["governance"]["status"], "superseded")
        self.assertEqual(str(old_doc["governance"]["superseded_by_memory_id"]), str(new_mem_id))

        # New memory is active
        new_doc = self.memory_repo.get_memory_by_id(self.user_id, new_mem_id)
        self.assertEqual(new_doc["governance"]["status"], "active")
        self.assertEqual(str(new_doc["governance"]["supersedes_memory_id"]), str(old_mem_id))

        # Only the $105k memory is returned in active retrieval
        active_mems = self.mem_service.retrieve_active_memories(self.user_id, memory_type="employment_income")
        self.assertTrue(any(str(m["_id"]) == str(new_mem_id) for m in active_mems))
        self.assertFalse(any(str(m["_id"]) == str(old_mem_id) for m in active_mems))

        # Check audit log
        logs = self.audit_repo.get_user_audit_logs(self.user_id)
        self.assertTrue(any(log["event_type"] == "memory_superseded" for log in logs))

    def test_delete_memory_governance(self):
        # Create a memory to delete
        prop = self.mem_service.propose_memory(
            user_id=self.user_id,
            memory_type="temporary_note",
            content="User mentioned looking at crypto investments",
            structured_data={},
            raw_statement="I might buy bitcoin",
            auto_confirm=True
        )
        mem_id = prop["memory_id"]

        # Delete memory
        deleted = self.mem_service.delete_memory(self.user_id, mem_id, reason="User requested erasure of crypto notes")
        self.assertTrue(deleted)

        # Inspect deleted document: content and embedding are wiped
        doc = self.memory_repo.get_memory_by_id(self.user_id, mem_id)
        self.assertEqual(doc["governance"]["status"], "deleted")
        self.assertEqual(doc["content"], "[DELETED BY USER]")
        self.assertIsNone(doc.get("embedding"))

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "user_id") and cls.user_id:
            uid = ObjectId(cls.user_id)
            cls.db["tax_profiles"].delete_many({"user_id": uid})
            cls.db["agent_memories"].delete_many({"user_id": uid})
            cls.db["audit_logs"].delete_many({"user_id": uid})
            cls.db["recommendations"].delete_many({"user_id": uid})
            cls.db["users"].delete_one({"_id": uid})

if __name__ == "__main__":
    unittest.main()

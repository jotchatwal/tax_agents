import unittest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.db.repositories import UserRepository

class TestApiEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        user_repo = UserRepository()
        alex = user_repo.get_by_email("alex@example.com")
        cls.user_id = str(alex["_id"]) if alex else None

    def test_01_health_check(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["connected"])

    def test_02_demo_users_endpoint(self):
        res = self.client.get("/api/users/demo")
        self.assertEqual(res.status_code, 200)
        users = res.json()
        self.assertGreaterEqual(len(users), 1)
        self.assertTrue(any(u["email"] == "alex@example.com" for u in users))

    def test_03_get_current_profile(self):
        headers = {"x-user-id": self.user_id} if self.user_id else {}
        res = self.client.get("/api/profile/current?tax_year=2025", headers=headers)
        self.assertEqual(res.status_code, 200)
        profile = res.json()
        self.assertIn("jurisdiction", profile)
        self.assertEqual(profile["jurisdiction"]["province"], "ON")

    def test_04_get_memories_endpoint(self):
        headers = {"x-user-id": self.user_id} if self.user_id else {}
        res = self.client.get("/api/memories?include_superseded=true", headers=headers)
        self.assertEqual(res.status_code, 200)
        mems = res.json()
        self.assertIsInstance(mems, list)
        self.assertGreaterEqual(len(mems), 1)

    def test_05_deterministic_rrsp_scenario_endpoint(self):
        payload = {
            "annual_income": 85000.0,
            "rrsp_contribution": 5000.0,
            "rrsp_limit": 18000.0,
            "tax_year": 2025
        }
        res = self.client.post("/api/scenarios/rrsp", json=payload)
        self.assertEqual(res.status_code, 200)
        calc = res.json()
        self.assertEqual(calc["calculation_status"], "calculated")
        self.assertAlmostEqual(calc["estimated_tax_saving"], 1482.50, delta=1.0)

    def test_06_audit_trail_endpoint(self):
        headers = {"x-user-id": self.user_id} if self.user_id else {}
        res = self.client.get("/api/audit", headers=headers)
        self.assertEqual(res.status_code, 200)

    def test_07_chat_endpoint(self):
        headers = {"x-user-id": self.user_id} if self.user_id else {}
        payload = {"message": "What tax planning opportunities do I have for 2025?", "session_id": "test_session"}
        res = self.client.post("/api/chat", json=payload, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("message", data)
        self.assertIn("recommendations", data)
        self.assertIsInstance(data["recommendations"], list)

if __name__ == "__main__":
    unittest.main()

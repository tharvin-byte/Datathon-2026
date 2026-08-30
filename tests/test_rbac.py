import io
import os
import sys
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from main import app  # noqa: E402
from routers.dataset import LOADED_DATASETS  # noqa: E402


class RbacTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        LOADED_DATASETS.clear()

    def login(self, role, district="Mysuru"):
        response = self.client.post("/auth/login", json={"role": role, "district": district})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def upload_csv(self, session_id):
        csv = (
            "case_id,date,district,crime_type,accused_name,victim_name,address,phone,"
            "co_accused_ids,IPC_section,description\n"
            "C001,2026-01-01,Mysuru,Burglary,Raju,Sita,MG Road,9000000000,,457,Initial report\n"
        )
        return self.client.post(
            "/dataset/upload",
            files={"file": ("cases.csv", io.BytesIO(csv.encode()), "text/csv")},
            data={"session_id": session_id},
        )

    def test_login_exposes_four_rank_categories(self):
        for role in ("local_officer", "investigator", "senior_officer", "admin"):
            response = self.login(role)
            self.assertEqual(response["rank"], role)
            self.assertIn("dashboard:view", response["permissions"])
        self.assertIn("dataset:upload", self.login("admin")["permissions"])
        self.assertNotIn("dataset:upload", self.login("local_officer")["permissions"])

    def test_only_admin_can_upload_dataset(self):
        local = self.login("local_officer")
        denied = self.upload_csv(local["session_id"])
        self.assertEqual(denied.status_code, 403)
        self.assertIn("dataset:upload", denied.json()["detail"])

        admin = self.login("admin")
        accepted = self.upload_csv(admin["session_id"])
        self.assertEqual(accepted.status_code, 200)
        self.assertIn("dataset_id", accepted.json())

    def test_local_officer_can_create_and_update_home_district_record(self):
        admin = self.login("admin")
        self.assertEqual(self.upload_csv(admin["session_id"]).status_code, 200)
        local = self.login("local_officer")

        created = self.client.post(
            "/records/create",
            json={
                "session_id": local["session_id"],
                "record": {
                    "case_id": "C002", "date": "2026-02-01", "district": "Mysuru",
                    "crime_type": "Theft", "accused_name": "Kiran", "description": "Field update"
                },
            },
        )
        self.assertEqual(created.status_code, 200)

        updated = self.client.post(
            "/records/update",
            json={"session_id": local["session_id"], "case_id": "C002", "updates": {"crime_type": "Robbery"}},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["record"]["crime_type"], "Robbery")
        dataset_id = updated.json()["dataset_id"]
        source_path = LOADED_DATASETS[dataset_id]["source_path"]
        with open(source_path, encoding="utf-8") as handle:
            persisted_csv = handle.read()
        self.assertIn("Robbery", persisted_csv)

    def test_local_officer_reads_only_home_district_records(self):
        admin = self.login("admin")
        csv = (
            "case_id,date,district,crime_type,accused_name,victim_name,address,phone,co_accused_ids,IPC_section,description\n"
            "C010,2026-01-01,Mysuru,Theft,Raju,Sita,MG Road,9000000000,,379,Local report\n"
            "C011,2026-01-01,Bengaluru,Theft,Kiran,Ravi,MG Road,9000000001,,379,Other district\n"
        )
        uploaded = self.client.post("/dataset/upload", files={"file": ("scope.csv", io.BytesIO(csv.encode()), "text/csv")}, data={"session_id": admin["session_id"]})
        self.assertEqual(uploaded.status_code, 200)
        local = self.login("local_officer", "Mysuru")
        response = self.client.get(f"/api/records?session_id={local['session_id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["case_id"] for row in response.json()["records"]], ["C010"])

    def test_senior_officer_has_statewide_investigation_scope(self):
        senior = self.login("senior_officer", "Mysuru")
        from backend.core.access_gate import check_access
        try:
            check_access({"role": senior["role"], "district": senior["district"]}, "Show cases in Bengaluru")
        except Exception as error:
            self.fail(f"Senior Officer should have statewide access: {error}")

    def test_local_officer_cannot_write_outside_home_district(self):
        admin = self.login("admin")
        self.assertEqual(self.upload_csv(admin["session_id"]).status_code, 200)
        local = self.login("local_officer", "Mysuru")
        denied = self.client.post(
            "/records/create",
            json={
                "session_id": local["session_id"],
                "record": {"case_id": "C003", "district": "Bengaluru", "crime_type": "Theft"},
            },
        )
        self.assertEqual(denied.status_code, 403)


if __name__ == "__main__":
    unittest.main()

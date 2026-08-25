import io
import os
import sys
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from main import app  # noqa: E402


class ApiSmokeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_datasets_endpoint_is_available(self):
        response = self.client.get("/api/datasets")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), dict)

    def test_investigation_without_dataset_returns_actionable_error(self):
        response = self.client.post(
            "/api/investigate",
            json={"session_id": "smoke-test", "query": "Show burglary trends"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("No dataset loaded", response.json()["detail"])

    def test_non_csv_upload_is_rejected(self):
        response = self.client.post(
            "/dataset/upload",
            files={"file": ("notes.txt", io.BytesIO(b"not csv"), "text/plain")},
            data={"session_id": "smoke-test"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Only CSV", response.json()["detail"])

    def test_cors_is_not_wildcard(self):
        response = self.client.get(
            "/api/datasets",
            headers={"Origin": "http://localhost:8001"},
        )
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:8001")


if __name__ == "__main__":
    unittest.main()

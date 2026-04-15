import importlib
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from fastapi.testclient import TestClient

main = importlib.import_module("src.main")


class MainApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_health_returns_expected_shape(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "version": "1.0.0"})

    def test_health_includes_cors_headers(self) -> None:
        response = self.client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://localhost:3000",
        )

    def test_upload_rejects_unsupported_file_types(self) -> None:
        response = self.client.post(
            "/upload",
            files={"file": ("malware.exe", b"boom", "application/octet-stream")},
            data={"company": "acme"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("Unsupported file type", response.json()["detail"])

    def test_upload_rejects_invalid_company_values(self) -> None:
        response = self.client.post(
            "/upload",
            files={"file": ("notes.txt", b"hello", "text/plain")},
            data={"company": "../bad"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("company must contain only letters", response.json()["detail"])

    def test_upload_returns_chunk_count_on_success(self) -> None:
        with patch("src.main.ingest_document", return_value=7):
            response = self.client.post(
                "/upload",
                files={"file": ("notes.txt", b"hello", "text/plain")},
                data={"company": "acme"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "message": "Document ingested successfully.",
                "collection": "acme",
                "chunk_count": 7,
            },
        )

    def test_upload_returns_502_without_raw_traceback_on_unexpected_error(self) -> None:
        with patch("src.main.ingest_document", side_effect=RuntimeError("boom")):
            response = self.client.post(
                "/upload",
                files={"file": ("notes.txt", b"hello", "text/plain")},
                data={"company": "acme"},
            )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "Ingestion failed: boom")
        self.assertNotIn("Traceback", response.text)

    def test_query_returns_structured_response(self) -> None:
        payload = {
            "answer": "Refunds are allowed within 30 days.",
            "sources": [{"content": "chunk", "source": "policy.pdf", "page": 2}],
            "confidence": 0.92,
            "declined": False,
        }
        with patch("src.main.query_brain", return_value=payload):
            response = self.client.post(
                "/query",
                json={"question": "What is the refund policy?", "company": "acme"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)

    def test_query_rejects_empty_or_too_long_questions(self) -> None:
        empty = self.client.post("/query", json={"question": "", "company": "acme"})
        long = self.client.post(
            "/query",
            json={"question": "x" * 501, "company": "acme"},
        )

        self.assertEqual(empty.status_code, 422)
        self.assertEqual(long.status_code, 422)

    def test_query_returns_404_for_missing_collection(self) -> None:
        with patch("src.main.query_brain", side_effect=RuntimeError("Collection not found")):
            response = self.client.post(
                "/query",
                json={"question": "Where is the handbook?", "company": "missing"},
            )

        self.assertEqual(response.status_code, 404)
        self.assertIn("Collection 'missing' not found", response.json()["detail"])

    def test_query_returns_503_without_raw_traceback_on_unexpected_error(self) -> None:
        with patch("src.main.query_brain", side_effect=RuntimeError("upstream timeout")):
            response = self.client.post(
                "/query",
                json={"question": "Where is the handbook?", "company": "acme"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Query failed: upstream timeout")
        self.assertNotIn("Traceback", response.text)


class StartupTests(unittest.TestCase):
    def test_main_import_fails_fast_without_api_key(self) -> None:
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)

        result = subprocess.run(
            [sys.executable, "-c", "import src.main"],
            cwd=os.getcwd(),
            env=env,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ValidationError", result.stderr)
        self.assertIn("openai_api_key", result.stderr)


if __name__ == "__main__":
    unittest.main()

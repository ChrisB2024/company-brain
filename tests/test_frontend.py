import importlib
import os
import unittest
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from fastapi.testclient import TestClient

main = importlib.import_module("src.main")


class FrontendServingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_root_serves_frontend_html(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("<title>Company Brain</title>", response.text)
        self.assertIn("Upload Document", response.text)
        self.assertIn("Ask a Question", response.text)

    def test_api_routes_still_take_priority_over_frontend(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "version": "1.0.0"})


class FrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = Path("frontend/index.html").read_text(encoding="utf-8")

    def test_upload_form_targets_expected_field_names(self) -> None:
        self.assertIn("formData.append('file', fileInput.files[0])", self.html)
        self.assertIn("formData.append('company', company)", self.html)
        self.assertIn("fetch(API_BASE + '/upload'", self.html)

    def test_query_form_posts_json_with_expected_schema(self) -> None:
        self.assertIn("fetch(API_BASE + '/query'", self.html)
        self.assertIn("headers: { 'Content-Type': 'application/json' }", self.html)
        self.assertIn("JSON.stringify({ question, company })", self.html)

    def test_frontend_uses_xss_safe_answer_rendering(self) -> None:
        self.assertIn("content.textContent = data.answer;", self.html)
        self.assertIn("function escapeHtml(text)", self.html)
        self.assertIn("div.textContent = text;", self.html)
        self.assertIn("escapeHtml(s.source)", self.html)

    def test_declined_responses_have_distinct_styling(self) -> None:
        self.assertIn(".answer-content.declined", self.html)
        self.assertIn("content.className = 'answer-content' + (data.declined ? ' declined' : '');", self.html)

    def test_confidence_bar_thresholds_match_claude_description(self) -> None:
        self.assertIn("data.confidence >= 0.75 ? '#22c55e'", self.html)
        self.assertIn(": data.confidence >= 0.5 ? '#eab308' : '#ef4444';", self.html)
        self.assertIn("fill.style.width = pct + '%';", self.html)

    def test_error_rendering_uses_structured_detail_messages(self) -> None:
        self.assertIn("data.detail || 'Upload failed.'", self.html)
        self.assertIn("data.detail || 'Query failed.'", self.html)
        self.assertIn("Network error: ' + err.message", self.html)

    def test_file_input_resets_after_successful_upload(self) -> None:
        self.assertIn("fileInput.value = '';", self.html)
        self.assertIn("document.getElementById('file-label').textContent = 'Choose a file...';", self.html)
        self.assertIn("document.getElementById('file-label').classList.remove('has-file');", self.html)

    def test_file_input_accept_restricts_supported_extensions(self) -> None:
        self.assertIn('accept=".pdf,.txt,.md"', self.html)


if __name__ == "__main__":
    unittest.main()

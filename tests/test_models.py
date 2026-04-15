import unittest

from pydantic import ValidationError

from src.models import QueryRequest, QueryResponse, SourceDocument, UploadResponse


class QueryRequestTests(unittest.TestCase):
    def test_accepts_valid_company_slug(self) -> None:
        request = QueryRequest(question="What is the refund policy?", company="acme-co_1")

        self.assertEqual(request.company, "acme-co_1")

    def test_rejects_company_names_with_special_characters(self) -> None:
        invalid_values = ["../secrets", "acme corp", "acme;drop", "acme/company"]

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    QueryRequest(question="What is the refund policy?", company=value)

    def test_rejects_empty_question(self) -> None:
        with self.assertRaises(ValidationError):
            QueryRequest(question="", company="default")

    def test_rejects_question_longer_than_500_chars(self) -> None:
        with self.assertRaises(ValidationError):
            QueryRequest(question="x" * 501, company="default")


class QueryResponseTests(unittest.TestCase):
    def test_requires_confidence(self) -> None:
        with self.assertRaises(ValidationError):
            QueryResponse(
                answer="Grounded answer",
                sources=[{"content": "chunk", "source": "doc.pdf"}],
            )

    def test_requires_sources(self) -> None:
        with self.assertRaises(ValidationError):
            QueryResponse(
                answer="Grounded answer",
                confidence=0.91,
            )

    def test_rejects_confidence_outside_unit_interval(self) -> None:
        invalid_values = [-0.01, 1.01]

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    QueryResponse(
                        answer="Grounded answer",
                        sources=[{"content": "chunk", "source": "doc.pdf"}],
                        confidence=value,
                    )


class SourceDocumentTests(unittest.TestCase):
    def test_page_is_optional(self) -> None:
        source = SourceDocument(content="chunk", source="doc.pdf")

        self.assertIsNone(source.page)


class UploadResponseTests(unittest.TestCase):
    def test_chunk_count_must_be_non_negative(self) -> None:
        with self.assertRaises(ValidationError):
            UploadResponse(
                message="ok",
                collection="default",
                chunk_count=-1,
            )


if __name__ == "__main__":
    unittest.main()

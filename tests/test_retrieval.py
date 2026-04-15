import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document
from pydantic import ValidationError

from src.models import QueryResponse
from src import retrieval


class QueryBrainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = SimpleNamespace(
            chroma_persist_dir="./chroma_db",
            retrieval_k=4,
            confidence_threshold=0.75,
            model_name="gpt-4o",
            temperature=0.0,
            openai_api_key=SimpleNamespace(get_secret_value=lambda: "test-key"),
        )

    def test_query_brain_declines_when_no_results(self) -> None:
        vectorstore = MagicMock()
        vectorstore.similarity_search_with_relevance_scores.return_value = []

        with patch("src.retrieval.get_settings", return_value=self.settings), patch(
            "src.retrieval.OpenAIEmbeddings", return_value="embeddings"
        ), patch("src.retrieval.Chroma", return_value=vectorstore), patch(
            "src.retrieval.ChatOpenAI"
        ) as mock_llm:
            response = retrieval.query_brain("What is our refund policy?", "acme")

        self.assertEqual(
            response,
            {
                "answer": "I couldn't find a confident answer in the provided documents.",
                "sources": [],
                "confidence": 0.0,
                "declined": True,
            },
        )
        mock_llm.assert_not_called()
        QueryResponse(**response)

    def test_query_brain_declines_below_threshold_without_llm_call(self) -> None:
        doc = Document(page_content="Refunds are case-by-case.", metadata={"source": "policy.pdf", "page": 2})
        vectorstore = MagicMock()
        vectorstore.similarity_search_with_relevance_scores.return_value = [(doc, 0.60)]

        with patch("src.retrieval.get_settings", return_value=self.settings), patch(
            "src.retrieval.OpenAIEmbeddings", return_value="embeddings"
        ), patch("src.retrieval.Chroma", return_value=vectorstore), patch(
            "src.retrieval.ChatOpenAI"
        ) as mock_llm:
            response = retrieval.query_brain("What is our refund policy?", "acme")

        self.assertTrue(response["declined"])
        self.assertEqual(response["confidence"], 0.60)
        self.assertEqual(response["sources"], [])
        mock_llm.assert_not_called()
        QueryResponse(**response)

    def test_query_brain_answers_above_threshold_with_sources(self) -> None:
        doc1 = Document(page_content="Refunds are allowed within 30 days.", metadata={"source": "policy.pdf", "page": 2})
        doc2 = Document(page_content="Customers must contact support for returns.", metadata={"source": "policy.pdf", "page": 2})
        vectorstore = MagicMock()
        vectorstore.similarity_search_with_relevance_scores.return_value = [(doc1, 0.91), (doc2, 0.85)]
        llm = MagicMock()
        llm.invoke.return_value = SimpleNamespace(content="Refunds are allowed within 30 days per policy.pdf.")

        with patch("src.retrieval.get_settings", return_value=self.settings), patch(
            "src.retrieval.OpenAIEmbeddings", return_value="embeddings"
        ) as mock_embeddings, patch(
            "src.retrieval.Chroma", return_value=vectorstore
        ) as mock_chroma, patch(
            "src.retrieval.ChatOpenAI", return_value=llm
        ) as mock_chat:
            response = retrieval.query_brain("What is our refund policy?", "acme")

        mock_embeddings.assert_called_once_with(api_key="test-key")
        mock_chroma.assert_called_once_with(
            collection_name="acme",
            embedding_function="embeddings",
            persist_directory="./chroma_db",
        )
        mock_chat.assert_called_once_with(
            model="gpt-4o",
            temperature=0.0,
            api_key="test-key",
        )
        llm.invoke.assert_called_once()
        messages = llm.invoke.call_args.args[0]
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], retrieval.SYSTEM_PROMPT)
        self.assertIn("ONLY the context above", messages[1]["content"])
        self.assertIn(doc1.page_content, messages[1]["content"])
        self.assertIn(doc2.page_content, messages[1]["content"])
        self.assertFalse(response["declined"])
        self.assertEqual(response["confidence"], 0.91)
        self.assertEqual(len(response["sources"]), 1)
        self.assertEqual(response["sources"][0]["source"], "policy.pdf")
        self.assertEqual(response["sources"][0]["page"], 2)
        QueryResponse(**response)

    def test_query_brain_propagates_collection_errors(self) -> None:
        with patch("src.retrieval.get_settings", return_value=self.settings), patch(
            "src.retrieval.OpenAIEmbeddings", return_value="embeddings"
        ), patch("src.retrieval.Chroma", side_effect=RuntimeError("Collection not found")):
            with self.assertRaises(RuntimeError):
                retrieval.query_brain("Where is the handbook?", "missing")


class HelperTests(unittest.TestCase):
    def test_extract_sources_deduplicates_by_source_and_page(self) -> None:
        doc1 = Document(page_content="A" * 250, metadata={"source": "handbook.pdf", "page": 1})
        doc2 = Document(page_content="B" * 50, metadata={"source": "handbook.pdf", "page": 1})
        doc3 = Document(page_content="C" * 50, metadata={"source": "faq.md", "page": None})

        sources = retrieval._extract_sources([(doc1, 0.9), (doc2, 0.8), (doc3, 0.7)])

        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0]["source"], "handbook.pdf")
        self.assertEqual(len(sources[0]["content"]), 200)
        self.assertEqual(sources[1]["source"], "faq.md")

    def test_declined_response_matches_query_response_schema(self) -> None:
        response = retrieval._declined_response(0.2)

        validated = QueryResponse(**response)

        self.assertTrue(validated.declined)
        self.assertEqual(validated.confidence, 0.2)

    def test_declined_response_rejects_invalid_confidence_via_schema(self) -> None:
        response = retrieval._declined_response(1.2)

        with self.assertRaises(ValidationError):
            QueryResponse(**response)


if __name__ == "__main__":
    unittest.main()

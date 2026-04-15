import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from src import ingest


class GetLoaderTests(unittest.TestCase):
    def test_get_loader_returns_pdf_loader_for_pdf_files(self) -> None:
        with patch("src.ingest.PyPDFLoader", return_value="pdf-loader") as mock_loader:
            loader = ingest._get_loader("/tmp/report.pdf")

        self.assertEqual(loader, "pdf-loader")
        mock_loader.assert_called_once_with("/tmp/report.pdf")

    def test_get_loader_returns_text_loader_for_text_and_markdown(self) -> None:
        with patch("src.ingest.TextLoader", return_value="text-loader") as mock_loader:
            txt_loader = ingest._get_loader("/tmp/notes.txt")
            md_loader = ingest._get_loader("/tmp/readme.md")

        self.assertEqual(txt_loader, "text-loader")
        self.assertEqual(md_loader, "text-loader")
        self.assertEqual(mock_loader.call_count, 2)

    def test_get_loader_rejects_unsupported_extensions(self) -> None:
        for file_name in ("/tmp/malware.exe", "/tmp/report.docx", "/tmp/data.csv"):
            with self.subTest(file_name=file_name):
                with self.assertRaises(ValueError):
                    ingest._get_loader(file_name)


class IngestDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = SimpleNamespace(
            chunk_size=500,
            chunk_overlap=50,
            chroma_persist_dir="./chroma_db",
            openai_api_key=SimpleNamespace(get_secret_value=lambda: "test-key"),
        )

    def _tmp_file(self, suffix: str = ".txt", content: str = "hello world") -> str:
        fd, path = tempfile.mkstemp(dir="/tmp", suffix=suffix)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def test_ingest_document_raises_for_missing_file(self) -> None:
        with patch("src.ingest.get_settings", return_value=self.settings):
            with self.assertRaises(FileNotFoundError):
                ingest.ingest_document("/tmp/does-not-exist.txt", "acme")

    def test_ingest_document_raises_for_oversized_file(self) -> None:
        path = self._tmp_file()

        try:
            with patch("src.ingest.get_settings", return_value=self.settings), patch(
                "src.ingest.os.path.getsize",
                return_value=(ingest.MAX_FILE_SIZE_MB + 1) * 1024 * 1024,
            ):
                with self.assertRaises(ValueError):
                    ingest.ingest_document(path, "acme")
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_ingest_document_cleans_up_oversized_tmp_file(self) -> None:
        path = self._tmp_file()

        with patch("src.ingest.get_settings", return_value=self.settings), patch(
            "src.ingest.os.path.getsize",
            return_value=(ingest.MAX_FILE_SIZE_MB + 1) * 1024 * 1024,
        ):
            with self.assertRaises(ValueError):
                ingest.ingest_document(path, "acme")

        try:
            self.assertFalse(
                os.path.exists(path),
                "Oversized /tmp files should be removed on failure per Claude's Session 2 cleanup claim.",
            )
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_ingest_document_raises_for_empty_documents_and_cleans_up_tmp_file(
        self,
    ) -> None:
        path = self._tmp_file()
        loader = MagicMock()
        loader.load.return_value = []

        with patch("src.ingest.get_settings", return_value=self.settings), patch(
            "src.ingest._get_loader", return_value=loader
        ):
            with self.assertRaises(ValueError):
                ingest.ingest_document(path, "acme")

        self.assertFalse(os.path.exists(path))

    def test_ingest_document_persists_chunks_with_basename_metadata(self) -> None:
        path = self._tmp_file(suffix=".md")
        documents = [
            Document(page_content="A short policy paragraph", metadata={"page": 3})
        ]
        chunks = [Document(page_content="chunk text", metadata={"page": 3})]
        loader = MagicMock()
        loader.load.return_value = documents
        splitter = MagicMock()
        splitter.split_documents.return_value = chunks

        with patch("src.ingest.get_settings", return_value=self.settings), patch(
            "src.ingest._get_loader", return_value=loader
        ), patch(
            "src.ingest.RecursiveCharacterTextSplitter", return_value=splitter
        ) as mock_splitter_class, patch(
            "src.ingest.OpenAIEmbeddings", return_value="embeddings"
        ) as mock_embeddings, patch(
            "src.ingest.Chroma.from_documents"
        ) as mock_from_documents:
            chunk_count = ingest.ingest_document(path, "acme")

        self.assertEqual(chunk_count, 1)
        self.assertEqual(documents[0].metadata["source"], os.path.basename(path))
        mock_splitter_class.assert_called_once_with(chunk_size=500, chunk_overlap=50)
        mock_embeddings.assert_called_once_with(api_key="test-key")
        mock_from_documents.assert_called_once_with(
            documents=chunks,
            embedding="embeddings",
            collection_name="acme",
            persist_directory="./chroma_db",
        )
        self.assertFalse(os.path.exists(path))

    def test_ingest_document_cleans_up_tmp_file_when_loader_rejects_file(self) -> None:
        path = self._tmp_file(suffix=".csv")

        with patch("src.ingest.get_settings", return_value=self.settings):
            with self.assertRaises(ValueError):
                ingest.ingest_document(path, "acme")

        self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()

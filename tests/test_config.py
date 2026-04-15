import os
import unittest

from pydantic import ValidationError

from src.config import Settings, get_settings


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_env = os.environ.copy()
        get_settings.cache_clear()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.original_env)
        get_settings.cache_clear()

    def test_settings_fail_fast_without_api_key(self) -> None:
        os.environ.pop("OPENAI_API_KEY", None)

        with self.assertRaises(ValidationError):
            Settings(_env_file=None)

    def test_settings_load_defaults_with_only_api_key(self) -> None:
        os.environ["OPENAI_API_KEY"] = "test-key"

        settings = Settings(_env_file=None)

        self.assertEqual(settings.chroma_persist_dir, "./chroma_db")
        self.assertEqual(settings.model_name, "gpt-4o")
        self.assertEqual(settings.temperature, 0.0)
        self.assertEqual(settings.chunk_size, 500)
        self.assertEqual(settings.chunk_overlap, 50)
        self.assertEqual(settings.retrieval_k, 4)
        self.assertEqual(settings.confidence_threshold, 0.75)

    def test_api_key_is_wrapped_as_secret(self) -> None:
        os.environ["OPENAI_API_KEY"] = "super-secret"

        settings = Settings(_env_file=None)

        self.assertEqual(settings.openai_api_key.get_secret_value(), "super-secret")
        self.assertNotIn("super-secret", repr(settings.openai_api_key))
        self.assertIn("**********", repr(settings.openai_api_key))

    def test_get_settings_returns_cached_instance(self) -> None:
        os.environ["OPENAI_API_KEY"] = "cached-key"

        first = get_settings()
        second = get_settings()

        self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()

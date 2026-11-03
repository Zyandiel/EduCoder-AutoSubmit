import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai.credentials import AIError, KEY_ENV, KEY_FILE, configure_api_key, get_api_key, save_api_key, validate_key


class CredentialsTests(unittest.TestCase):
    def test_environment_priority_and_missing_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {}, clear=True):
                self.assertIsNone(get_api_key(root))
            with patch.dict(os.environ, {KEY_ENV: "  sk-environment-test-key  "}):
                with patch("ai.credentials._protect") as decrypt:
                    self.assertEqual(get_api_key(root), "sk-environment-test-key")
                    decrypt.assert_not_called()

    def test_invalid_key_does_not_appear_in_error(self):
        for value in (None, "", "short", "secret\nBAD", "secret\rHEADER", "secret 含空格"):
            with self.subTest(value=value), self.assertRaises(AIError) as error:
                validate_key(value)
            self.assertNotIn("secret", str(error.exception))

    @unittest.skipUnless(os.name == "nt", "DPAPI is specific to Windows")
    def test_dpapi_roundtrip_and_file_is_not_plaintext(self):
        key = "sk-dpapi-unit-test-placeholder"
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            save_api_key(root, key)
            path = root / ".auth" / KEY_FILE
            self.assertNotIn(key.encode(), path.read_bytes())
            self.assertEqual(get_api_key(root), key)
            self.assertEqual(list(path.parent.iterdir()), [path])

    @unittest.skipUnless(os.name == "nt", "DPAPI is specific to Windows")
    def test_corrupted_dpapi_file_is_reported_without_contents(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            path = root / ".auth" / KEY_FILE
            path.parent.mkdir()
            path.write_bytes(b"secret-corrupted-file")
            with self.assertRaises(AIError) as error:
                get_api_key(root)
            self.assertTrue(error.exception.fatal_run)
            self.assertNotIn("secret", str(error.exception))

    def test_save_failure_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".auth" / KEY_FILE
            path.parent.mkdir()
            path.write_bytes(b"previous-ciphertext")
            with patch("ai.credentials._protect", return_value=b"new-ciphertext"), \
                    patch("ai.credentials.os.replace", side_effect=OSError("replacement failed")):
                with self.assertRaises(OSError):
                    save_api_key(root, "sk-unit-test-placeholder")
            self.assertEqual(path.read_bytes(), b"previous-ciphertext")
            self.assertEqual(list(path.parent.iterdir()), [path])

    @unittest.skipUnless(os.name == "nt", "Windows hidden input setup")
    def test_interactive_setup_does_not_echo_key(self):
        import io
        key = "sk-getpass-test-placeholder"
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            output = io.StringIO()
            with patch("ai.credentials.getpass.getpass", return_value=key), patch("sys.stdout", output):
                self.assertEqual(configure_api_key(Path(directory)), key)
            self.assertNotIn(key, output.getvalue())


if __name__ == "__main__":
    unittest.main()

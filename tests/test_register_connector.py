import importlib.util
import os
import unittest

MODULE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "adapters", "mistral", "register_connector.py")
spec = importlib.util.spec_from_file_location("register_connector", MODULE_PATH)
register_connector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(register_connector)


class RegisterConnectorTest(unittest.TestCase):
    def test_connector_payload_shape(self):
        payload = register_connector.build_connector_payload(
            "seafile", "https://seafile.example.org/", "private", "desc")
        self.assertEqual(payload["protocol"], "http")
        self.assertEqual(payload["server"], "https://seafile.example.org")
        self.assertEqual(payload["visibility"], "private")
        self.assertEqual(payload["name"], "seafile")

    def test_credentials_payload_uses_token_scheme(self):
        payload = register_connector.build_credentials_payload(
            "user", "seafile-default", "abc123")
        self.assertEqual(
            payload["credentials"]["headers"]["Authorization"], "Token abc123")
        self.assertTrue(payload["is_default"])

    def test_credentials_payload_passthrough(self):
        payload = register_connector.build_credentials_payload(
            "workspace", "x", "Bearer abc")
        self.assertEqual(
            payload["credentials"]["headers"]["Authorization"], "Bearer abc")

    def test_redact_hides_token(self):
        payload = register_connector.build_credentials_payload(
            "user", "c", "super-secret-token")
        redacted = register_connector.redact(payload, "super-secret-token")
        rendered = str(redacted)
        self.assertNotIn("super-secret-token", rendered)
        self.assertIn("***", rendered)


if __name__ == "__main__":
    unittest.main()

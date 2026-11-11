import os
import unittest

from apple_store_mcp.shop.http import validate_proxy_environment, request_error
from apple_store_mcp.shop.errors import RetailerError


class TestProxy(unittest.TestCase):
    def setUp(self):
        for k in ("APPLE_STORE_PROXY", "APPLE_STORE_PROXY_FILE", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
            os.environ.pop(k, None)

    def test_obsolete_settings_rejected(self):
        os.environ["APPLE_STORE_PROXY"] = "http://x"
        with self.assertRaises(RetailerError):
            validate_proxy_environment()

    def test_request_error_no_credentials(self):
        exc = Exception("proxy authentication failed for http://user:pass@proxy")
        err = request_error("ctx", exc)
        self.assertIn("proxy", str(err).lower())
        # credentials should not be added by us; message uses generic text
        self.assertNotIn("pass", str(err))

    def test_classify_blocked(self):
        err = RetailerError("Request was blocked (HTTP 403).")
        self.assertEqual(err.code, "blocked")


if __name__ == "__main__":
    unittest.main()
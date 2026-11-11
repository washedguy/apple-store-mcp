import unittest
from apple_store_mcp.shop.config import STOREFRONTS, path_prefix, site_prefix


class TestStorefronts(unittest.TestCase):
    def test_supported_countries(self):
        self.assertIn("us", STOREFRONTS)
        self.assertIn("de", STOREFRONTS)
        self.assertIn("ch", STOREFRONTS)
        self.assertIn("be", STOREFRONTS)

    def test_languages(self):
        self.assertEqual(STOREFRONTS["ch"][2], ("de", "fr"))
        self.assertEqual(STOREFRONTS["be"][2], ("fr", "nl"))

    def test_invalid_country(self):
        self.assertNotIn("xx", STOREFRONTS)

    def test_path_prefix(self):
        self.assertEqual(path_prefix("ch", "de"), "ch-de")
        self.assertEqual(path_prefix("us", "en"), "us")

    def test_site_prefix(self):
        self.assertEqual(site_prefix("ch", "de"), "chde")
        self.assertEqual(site_prefix("be", "fr"), "befr")
        self.assertEqual(site_prefix("de", "de"), "de")


if __name__ == "__main__":
    unittest.main()
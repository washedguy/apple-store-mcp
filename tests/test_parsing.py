import os
import unittest

from apple_store_mcp.shop.parsing import parse_search, parse_product_page, parse_store_list

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class TestParsing(unittest.TestCase):
    def test_search_explore(self):
        html = open(os.path.join(FIX, "search_us_explore.html"), encoding="utf-8").read()
        r = parse_search(html, "https://www.apple.com", "us", "en", "iphone", "explore", 1)
        self.assertEqual(r["query"], "iphone")
        self.assertGreater(len(r["products"]), 0)
        self.assertTrue(r["hasNextResults"] if "hasNextResults" in r else True)
        self.assertIsNotNone(r["next_page"])

    def test_search_accessories(self):
        html = open(os.path.join(FIX, "search_us_accessories.html"), encoding="utf-8").read()
        r = parse_search(html, "https://www.apple.com", "us", "en", "iphone", "accessories", 1)
        self.assertEqual(r["tab"], "accessories")
        self.assertGreater(len(r["products"]), 0)
        p = r["products"][0]
        self.assertIsNotNone(p["id"])
        self.assertIsNotNone(p["price"])
        self.assertEqual(p["currency"], "USD")

    def test_product_page(self):
        html = open(os.path.join(FIX, "product_us_buy.html"), encoding="utf-8").read()
        d = parse_product_page(html, "https://www.apple.com/shop/buy-iphone/iphone-17", "https://www.apple.com")
        self.assertEqual(d["title"], "iPhone 17")
        self.assertEqual(d["price"], 899.0)
        self.assertEqual(d["currency"], "USD")

    def test_store_list(self):
        html = open(os.path.join(FIX, "storelist_de.html"), encoding="utf-8").read()
        entries = parse_store_list(html, "https://www.apple.com", "de", "de")
        self.assertGreater(len(entries), 0)
        self.assertTrue(any("Sindelfingen" in e["name"] for e in entries))
        self.assertFalse(any(e["name"] in ("Genius Bar", "Für Unternehmen einkaufen") for e in entries))

    def test_store_list_us(self):
        html = open(os.path.join(FIX, "storelist_us.html"), encoding="utf-8").read()
        entries = parse_store_list(html, "https://www.apple.com", "us", "en")
        self.assertGreater(len(entries), 100)

    def test_preorder_detection(self):
        html = '''<script type="application/ld+json">{"@type":"Product","name":"X","offers":{"@type":"Offer","price":10,"priceCurrency":"USD","availability":"https://schema.org/PreOrder","sku":"X1"}}</script>'''
        d = parse_product_page(html, "https://www.apple.com/x", "https://www.apple.com")
        self.assertEqual(d["delivery"]["status"], "preorder")
        self.assertTrue(d["preorder"])
        self.assertTrue(d["is_preorder"])


if __name__ == "__main__":
    unittest.main()

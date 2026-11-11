import asyncio
import json
import unittest
from unittest.mock import patch

from apple_store_mcp.client import Client
from apple_store_mcp.shop.configurator import parse_configuration
from apple_store_mcp.shop.errors import RetailerError


class ConfiguratorTests(unittest.TestCase):
    def test_compatibility_and_relative_prices(self):
        response = {"body": {"options": {"memory": {"compatibleOptions": {
            "16gb": {"priceDelta": "zero", "isDefault": True},
            "32gb": {"priceDelta": "440", "isBlocked": False}},
            "upgradeOptions": {"128gb": {"isBlocked": False}}}},
            "prices": {"zero": {"amount": 0}, "440": {"amount": 440, "displayPrice": "+ 440 €"}},
            "selectedKits": {"dimensions": {"memory": {"dimensionValue": "16gb"}}, "priceData": {"amount": 2464, "comparativeDisplayPrice": "From <span>€2,464</span>"}}}}
        result = parse_configuration(json.dumps(response), "EUR")
        choices = result["dimensions"][0]["choices"]
        self.assertEqual(choices[1]["price_delta"], 440)
        self.assertEqual(choices[2]["category"], "upgrade")
        self.assertIsNone(choices[2]["price_delta"])
        self.assertEqual(result["selected_dimensions"]["memory"], "16gb")
        self.assertEqual(result["selected_price"], 2464)
        self.assertEqual(result["selected_price_display"], "From €2,464")

    def test_rejects_invalid_response_and_identifiers(self):
        with self.assertRaises(RetailerError):
            parse_configuration('{"body":{"isReset":false}}', "EUR")
        with self.assertRaises(RetailerError):
            asyncio.run(Client('de').configuration('invalid&collection', {}))

    def test_url_and_request(self):
        async def fetch(url, **kwargs):
            self.assertIn('/de/shop/api/cto/update-config?', url)
            self.assertIn('sv.memory-dimensionMemory=32gb', url)
            return '{"body":{"options":{},"prices":{}}}', url
        with patch('apple_store_mcp.shop.configurator.fetch_text', fetch):
            result = asyncio.run(Client('de').configuration('MBP_2026_COLLECTION', {'memory-dimensionMemory': '32gb'}))
        self.assertEqual(result['currency'], 'EUR')

class ProductGroupTests(unittest.TestCase):
    def test_variant_attributes_remain_attached_to_their_prices(self):
        from apple_store_mcp.shop.parsing import parse_product_page
        group = {"@type": "ProductGroup", "name": "Tablet", "hasVariant": [
            {"sku": "B", "name": "Large", "additionalProperty": [{"name": "Storage", "value": "2TB"}],
             "offers": {"price": 1200, "priceCurrency": "USD", "url": "https://www.apple.com/b"}},
            {"sku": "A", "name": "Small", "additionalProperty": [{"name": "Storage", "value": "256GB"}],
             "offers": {"price": 800, "priceCurrency": "USD", "url": "https://www.apple.com/a"}}]}
        html = '<script type="application/ld+json">' + json.dumps(group) + '</script>'
        result = parse_product_page(html, 'https://www.apple.com/test', 'https://www.apple.com')
        self.assertEqual(result['price'], 800)
        self.assertEqual(result['variant_prices'][0]['attributes']['Storage'], '2TB')
        self.assertEqual(result['variant_prices'][0]['price'], 1200)

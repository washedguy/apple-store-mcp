import asyncio
import json
import unittest
from unittest.mock import patch

from apple_store_mcp.client import Client
from apple_store_mcp.shop.browse import _labels, _resolve_requested, browse
from apple_store_mcp.shop.errors import RetailerError


class BrowseTests(unittest.TestCase):
    def test_discover_page_choices_excludes_navigation(self):
        html = ('<nav><a href="/de/shop/goto/buy_misc">Other</a></nav>'
                '<main><a href="/de/shop/goto/buy_mac/example" aria-label="Buy Example">Buy</a></main>')
        async def fetch(url, **kwargs):
            return html, url
        with patch('apple_store_mcp.shop.browse.fetch_text', fetch):
            result = asyncio.run(browse(Client('de'), 'https://www.apple.com/de/example/'))
        self.assertEqual(result['choices'], [{'name': 'Buy Example', 'url': 'https://www.apple.com/de/shop/goto/buy_mac/example'}])

    def test_readable_choice_selection_and_invalid_values(self):
        data = {'mainDisplayValues': {}, 'configDisplayValues': {
            'memory-dimensionMemory': {'24gb': {'header': '24&nbsp;GB'}, '48gb': {'header': '48&nbsp;GB<div>description</div>'}}}}
        labels = _labels(data)
        self.assertEqual(_resolve_requested({'memory': '48 GB'}, labels), {'memory-dimensionMemory': '48gb'})
        with self.assertRaises(RetailerError):
            _resolve_requested({'memory': '128 GB'}, labels)

    def test_configurator_derives_base_and_applies_readable_options(self):
        metadata = {'products': [{'priceKey': 'base', 'dimensions': {'chassis-dimensionScreensize': '14inch'}}],
                    'mainDisplayValues': {'prices': {'base': {'amount': 100}}, 'chassis-dimensionScreensize': {'14inch': {'header': '14 inches'}}},
                    'configDisplayValues': {'memory-dimensionMemory': {'24gb': {'header': '24 GB'}, '48gb': {'header': '48 GB'}}}}
        html = 'productSelectionData: ' + json.dumps(metadata) + ' collection=TEST_COLLECTION'
        async def fetch(url, **kwargs):
            return html, url
        async def config(client, collection, selections):
            self.assertEqual(selections, {'chassis-dimensionScreensize': '14inch', 'memory-dimensionMemory': '48gb'})
            return {'reset': False, 'selected_dimensions': selections, 'currency': 'EUR', 'selected_price': 120,
                    'selected_price_display': 'From €120', 'observed_at': 'now', 'dimensions': [
                        {'name': 'memory-dimensionMemory', 'choices': [
                            {'value': '48gb', 'category': 'compatible', 'blocked': False, 'price_delta': 0}]}]}
        with patch('apple_store_mcp.shop.browse.fetch_text', fetch), patch('apple_store_mcp.shop.browse.configuration', config):
            result = asyncio.run(browse(Client('de'), 'https://www.apple.com/de/shop/buy-mac/test', {'memory': '48 GB'}))
        self.assertEqual(result['selection'], {'memory': '48 GB'})
        self.assertEqual(result['price'], 120)

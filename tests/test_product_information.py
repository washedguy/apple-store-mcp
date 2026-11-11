import asyncio
import unittest
from unittest.mock import patch
from apple_store_mcp.client import Client
from apple_store_mcp.shop.product_info import product_info


class ProductInformationTests(unittest.TestCase):
    def test_base_prices_and_contextual_upgrade_requirements(self):
        async def fake_overview(client, product, options, location, postcode):
            return {'kind': 'products', 'product': 'Example', 'country': 'de', 'url': 'https://www.apple.com/de/shop/buy-mac/example',
                    'observed_at': 'now', 'currency': 'EUR', 'variants': [
                        {'attributes': {'screen_size': '14 inch', 'chip': 'Pro'}, 'price': 1000},
                        {'attributes': {'screen_size': '16 inch', 'chip': 'Pro'}, 'price': 1500}],
                    'available_options': [{'name': 'memory', 'values': ['24 GB', '48 GB', '128 GB']}]}
        async def fake_browse(client, url, requested):
            return {'kind': 'configuration', 'selection': {'chip': 'Pro', 'screen_size': '14 inch', 'memory': '24 GB'},
                    'options': [{'name': 'memory', 'choices': [
                        {'name': '24 GB', 'compatible': True, 'requires_changes': False, 'price_change': 0},
                        {'name': '48 GB', 'compatible': True, 'requires_changes': False, 'price_change': 300},
                        {'name': '128 GB', 'compatible': False, 'requires_changes': True, 'price_change': None}]}]}
        async def run():
            with patch('apple_store_mcp.shop.product_info.overview', fake_overview), patch('apple_store_mcp.shop.product_info.browse', fake_browse):
                return await product_info(Client('de'), 'Example')
        result = asyncio.run(run())
        self.assertEqual(result['options']['screen_size'][1]['price']['amount'], 1500)
        memory = {x['name']: x for x in result['options']['memory']}
        self.assertEqual(memory['48 GB']['price']['kind'], 'change_from_example')
        self.assertEqual(memory['48 GB']['price']['amount'], 300)
        self.assertEqual(memory['128 GB']['requirements'][0]['status'], 'requires_changes')
        self.assertEqual(memory['128 GB']['requirements'][0]['when'], 'example_1')
        self.assertEqual(result['example_configuration']['chip'], 'Pro')
        self.assertIsNone(memory['128 GB']['price'])

    def test_discrete_variants_group_actual_prices(self):
        async def fake_overview(client, product, options, location, postcode):
            return {'kind': 'products', 'product': 'Phone', 'country': 'de', 'url': 'https://www.apple.com/de/shop/buy-iphone/phone',
                    'observed_at': 'now', 'currency': 'EUR', 'variants': [
                        {'attributes': {'color': 'Blue', 'capacity': '256 GB'}, 'price': 900, 'part_number': 'A'},
                        {'attributes': {'color': 'Blue', 'capacity': '512 GB'}, 'price': 1100, 'part_number': 'B'}]}
        with patch('apple_store_mcp.shop.product_info.overview', fake_overview):
            result = asyncio.run(product_info(Client('de'), 'Phone'))
        self.assertEqual(result['options']['color'][0]['price']['amount'], 900)
        self.assertEqual(result['options']['capacity'][1]['price']['amount'], 1100)
        self.assertIsNone(result.get('example_configuration'))

    def test_requirements_are_scoped_to_each_tested_chip(self):
        async def fake_overview(client, product, options, location, postcode):
            return {'kind': 'products', 'product': 'Example', 'country': 'de', 'url': 'https://www.apple.com/de/shop/buy-mac/example',
                    'observed_at': 'now', 'currency': 'EUR', 'variants': [
                        {'attributes': {'chip': 'Pro', 'cpu_gpu': '10 cores'}, 'price': 1000},
                        {'attributes': {'chip': 'Max', 'cpu_gpu': '20 cores'}, 'price': 2000}]}
        async def fake_browse(client, url, requested):
            is_max = requested.get('chip') == 'Max'
            return {'kind': 'configuration', 'selection': {'chip': 'Max' if is_max else 'Pro',
                    'cpu_gpu': '20 cores' if is_max else '10 cores'}, 'options': [
                    {'name': 'memory', 'choices': [{'name': '128 GB', 'compatible': is_max,
                     'requires_changes': not is_max, 'price_change': 500 if is_max else None}]}]}
        async def run():
            with patch('apple_store_mcp.shop.product_info.overview', fake_overview), patch('apple_store_mcp.shop.product_info.browse', fake_browse):
                return await product_info(Client('de'), 'Example')
        result = asyncio.run(run())
        memory = result['options']['memory'][0]
        self.assertEqual([r['status'] for r in memory['requirements']], ['requires_changes', 'compatible'])
        self.assertEqual(memory['requirements'][1]['price_change']['amount'], 500)
        self.assertEqual(result['example_configurations']['example_2']['chip'], 'Max')

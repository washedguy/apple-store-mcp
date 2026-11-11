import json
import asyncio
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

from apple_store_mcp.client import Client
from apple_store_mcp.shop.delivery import configuration_delivery, parse_delivery
from apple_store_mcp.shop.parsing import parse_catalog_variants
from apple_store_mcp.shop.errors import RetailerError


class DeliveryVariantTests(unittest.TestCase):
    def test_each_part_keeps_its_color_storage_and_price(self):
        data = {'products': [{'partNumber': 'A', 'fullPrice': 'a', 'dimensionColor': 'white', 'dimensionCapacity': '256gb'},
                             {'partNumber': 'B', 'fullPrice': 'b', 'dimensionColor': 'black', 'dimensionCapacity': '256gb'}],
                'displayValues': {'dimensionColor': {'white': {'value': 'White'}, 'black': {'value': 'Black'}},
                                  'dimensionCapacity': {'256gb': {'value': '256 <small>GB</small>'}},
                                  'prices': {'a': {'amountBeforeTradeIn': 100, 'priceCurrency': 'EUR'},
                                             'b': {'amountBeforeTradeIn': 100, 'priceCurrency': 'EUR'}}}}
        variants = parse_catalog_variants('productSelectionData: ' + json.dumps(data))
        self.assertEqual(len(variants), 2)
        self.assertEqual(variants[1]['attributes'], {'color': 'Black', 'capacity': '256 GB'})
        self.assertEqual(variants[1]['part_number'], 'B')
        self.assertEqual(variants[1]['price'], 100)

    def test_delivery_preserves_estimate_and_missing_is_unknown(self):
        data = {'body': {'content': {'deliveryMessage': {'A': {'regular': {'subHeader': 'For A',
            'deliveryOptions': [{'displayName': 'Express', 'date': 'Monday', 'shippingCost': 'Free'}]}}}}}}
        results = parse_delivery(json.dumps(data), ['A', 'B'])
        self.assertEqual(results[0]['options'][0]['date'], 'Monday')
        self.assertIsNone(results[1]['available'])
        self.assertEqual(results[1]['options'], [])
        with self.assertRaises(RetailerError):
            parse_delivery('{}', ['A'])

    def test_configuration_delivery_uses_exact_composite_key(self):
        data = {'body': {'content': {'deliveryMessage': {
            'PARTKITA KITB'.replace(' ', ''): {'regular': {'deliveryOptions': [
                {'displayName': 'Express', 'date': 'Friday', 'shippingCost': 'Free'}]}}}}}}
        result = parse_delivery(json.dumps(data), ['PART'], response_keys={'PART': 'PARTKITAKITB'})
        self.assertEqual(result[0]['options'][0]['date'], 'Friday')
        self.assertEqual(parse_delivery(json.dumps(data), ['PART'])[0]['options'], [])

    def test_configuration_delivery_keeps_session_and_selection(self):
        session_id = object()
        @asynccontextmanager
        async def session_factory(**kwargs):
            yield session_id
        async def fetch(url, *, session, **kwargs):
            self.assertIs(session, session_id)
            if '/delivery-message?' in url:
                payload = {'body': {'content': {'deliveryMessage': {'PARTKITAKITB': {'regular': {
                    'deliveryOptions': [{'displayName': 'Express', 'date': 'Friday', 'shippingCost': 'Free'}]}}}}}}
                return json.dumps(payload), url
            return 'PRODUCT_SELECTION_BOOTSTRAP', url
        async def config(client, collection, selections, *, session, referer):
            self.assertIs(session, session_id)
            return {'reset': False, 'selected_dimensions': selections, 'container_part_number': 'PART',
                    'product_configuration': {'second': 'KITB', 'first': 'KITA'}}
        async def run():
            with patch('apple_store_mcp.shop.delivery._session', session_factory), \
                 patch('apple_store_mcp.shop.delivery.fetch_text', fetch), \
                 patch('apple_store_mcp.shop.delivery.configuration', config):
                return await configuration_delivery(Client('de'), 'https://www.apple.com/de/shop/buy-mac/example',
                                                    'COLLECTION', {'memory': '32gb'}, '10115')
        result = asyncio.run(run())
        self.assertEqual(result['products'][0]['options'][0]['date'], 'Friday')
        self.assertEqual(result['configuration']['selected_dimensions']['memory'], '32gb')

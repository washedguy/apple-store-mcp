import asyncio
import json
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

from apple_store_mcp.client import Client
from apple_store_mcp.shop.errors import RetailerError
from apple_store_mcp.shop.fulfillment import fulfillment, parse_fulfillment


class FulfillmentTests(unittest.TestCase):
    def test_request_uses_new_session_for_each_flow(self):
        sessions = []
        calls = []
        @asynccontextmanager
        async def session_factory(**kwargs):
            session = object()
            sessions.append(session)
            yield session
        async def fetch(url, *, session, **kwargs):
            calls.append((session, url))
            if '/retail/pickup-message?' in url:
                return json.dumps({'body': {'stores': [
                    {'storeNumber': 'R1', 'storeName': 'Test', 'city': 'Test City',
                     'partsAvailability': {'part': {'storePickEligible': True,
                                                   'pickupDisplay': 'ships-to-store',
                                                   'pickupSearchQuote': 'Tomorrow'}}}]}}), url
            return 'PRODUCT_SELECTION_BOOTSTRAP', url
        async def config(client, collection, selections, *, session, referer):
            calls.append((session, 'config'))
            return {'reset': False, 'selected_dimensions': selections,
                    'container_part_number': 'PART', 'product_configuration': {'memory': 'KIT'}}
        async def run():
            with patch('apple_store_mcp.shop.fulfillment._session', session_factory), \
                 patch('apple_store_mcp.shop.fulfillment.fetch_text', fetch), \
                 patch('apple_store_mcp.shop.fulfillment.configuration', config):
                for _ in range(2):
                    result = await fulfillment(Client('de'), 'https://www.apple.com/de/shop/buy-mac/macbook-pro',
                                               'COLLECTION', {'memory': '32gb'}, '10115')
                    self.assertEqual(result['stores'][0]['availability'][0]['display'], 'ships-to-store')
                    self.assertEqual(result['stores'][0]['availability'][0]['status'], 'ships_to_store')
                    self.assertEqual(result['configuration']['selected_dimensions']['memory'], '32gb')
        asyncio.run(run())
        self.assertEqual(len(sessions), 2)
        self.assertIsNot(sessions[0], sessions[1])
        self.assertTrue(all(call[0] is sessions[0] for call in calls[:3]))
        self.assertTrue(all(call[0] is sessions[1] for call in calls[3:]))

    def test_missing_pickup_is_not_reported_as_no_stores(self):
        with self.assertRaises(RetailerError):
            parse_fulfillment('{"body":{"content":{}}}')

    def test_unknown_codes_are_not_treated_as_available(self):
        payload = {'body': {'stores': [{'partsAvailability': {'p': {
            'storePickEligible': True, 'pickupDisplay': 'new-code'}}}]}}
        self.assertEqual(parse_fulfillment(json.dumps(payload))[0]['availability'][0]['status'], 'unknown')

    def test_each_pickup_quote_keeps_the_variant_part_number(self):
        payload = {'body': {'stores': [{'partsAvailability': {
            'A': {'partNumber': 'A', 'pickupDisplay': 'available'},
            'B': {'partNumber': 'B', 'pickupDisplay': 'unavailable'}}}]}}
        quotes = parse_fulfillment(json.dumps(payload))[0]['availability']
        self.assertEqual([(x['part_number'], x['status']) for x in quotes],
                         [('A', 'available'), ('B', 'unavailable')])

    def test_invalid_buy_url_is_rejected(self):
        with self.assertRaises(RetailerError):
            asyncio.run(fulfillment(Client('de'), 'https://example.com/de/shop/buy-mac/x', 'C', {}, '10115'))

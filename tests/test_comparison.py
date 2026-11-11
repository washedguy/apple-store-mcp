import asyncio
import unittest
from unittest.mock import patch

from apple_store_mcp.client import Client
from apple_store_mcp.shop.comparison import compare
from apple_store_mcp.shop.errors import RetailerError


class ComparisonTests(unittest.TestCase):
    def test_partial_failure_and_unchecked_stores_are_explicit(self):
        async def directory(client):
            return {'stores': [{'id': 'R1', 'name': 'One', 'url': 'one'}, {'id': 'R2', 'name': 'Two', 'url': 'two'}]}
        async def enrich(client, entry):
            return {'address': {'city': entry['name']}}
        async def pickup(client, url, parts, location):
            if location == 'Two':
                raise RetailerError('Blocked', code='blocked')
            return {'observed_at': 'now', 'stores': [{'id': 'R1', 'name': 'One', 'city': 'One',
                    'availability': [{'part_number': 'A', 'status': 'available'}]}]}
        async def delivery(client, url, parts, postal):
            raise RetailerError('Temporarily blocked', code='blocked')
        async def run():
            with patch('apple_store_mcp.shop.comparison.list_all', directory), patch('apple_store_mcp.shop.comparison._enrich', enrich), \
                 patch('apple_store_mcp.shop.comparison.variant_pickup', pickup), patch('apple_store_mcp.shop.comparison.delivery', delivery):
                return await compare(Client('de'), 'url', ['A', 'B'], [], ['12345'], True)
        result = asyncio.run(run())
        self.assertFalse(result['complete'])
        self.assertEqual(result['missing_stores'], [{'id': 'R2', 'name': 'Two'}])
        self.assertEqual(result['missing_parts'], [{'store_id': 'R1', 'part_number': 'B'}])
        self.assertEqual([e['stage'] for e in result['errors']], ['pickup', 'delivery'])
        self.assertEqual(result['pickup'][0]['availability'][0]['status'], 'available')

    def test_unknown_quotes_and_missing_delivery_are_not_complete(self):
        async def pickup(client, url, parts, location):
            return {'observed_at': 'now', 'stores': [{'id': 'R1', 'name': 'One', 'city': 'One',
                    'availability': [{'part_number': 'A', 'status': 'unknown'}]}]}
        async def delivery(client, url, parts, postal):
            return {'postal_code': postal, 'products': [{'part_number': 'A', 'options': []}]}
        async def run():
            with patch('apple_store_mcp.shop.comparison.variant_pickup', pickup), \
                 patch('apple_store_mcp.shop.comparison.delivery', delivery):
                return await compare(Client('de'), 'url', ['A'], ['Berlin'], ['10115'])
        result = asyncio.run(run())
        self.assertFalse(result['complete'])
        self.assertEqual(result['unknown_parts'], [{'store_id': 'R1', 'part_number': 'A'}])
        self.assertEqual(result['unknown_delivery'], [{'postal_code': '10115', 'part_number': 'A'}])

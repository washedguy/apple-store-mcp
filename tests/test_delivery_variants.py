import json
import unittest

from apple_store_mcp.shop.delivery import parse_delivery
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

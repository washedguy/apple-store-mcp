"""Sanitized Apple page data recorded on 2026-11-11; tests run offline."""
import json
import unittest
from pathlib import Path
from apple_store_mcp.shop.parsing import parse_catalog_variants, parse_product_page

FIXTURES = Path(__file__).parent / 'fixtures'


class RecordedCatalogTests(unittest.TestCase):
    def test_discrete_variants_for_german_and_french_canadian_stores(self):
        for name, currency in [('iphone_duo_de.json', 'EUR'), ('iphone_duo_ca_fr.json', 'CAD'),
                               ('iphone_duo_ch_fr.json', 'CHF'), ('iphone_duo_be_nl.json', 'EUR'),
                               ('iphone_duo_jp.json', 'JPY')]:
            with self.subTest(fixture=name):
                text = (FIXTURES / name).read_text(encoding='utf-8')
                variants = parse_catalog_variants('productSelectionData: ' + text)
                self.assertEqual(len(variants), 8)
                self.assertEqual(len({v['part_number'] for v in variants}), 8)
                self.assertTrue(all(v['currency'] == currency and v['price'] > 0 for v in variants))
                self.assertEqual(len({v['attributes']['color'] for v in variants}), 2)
                self.assertEqual(len({v['attributes']['capacity'] for v in variants}), 4)

    def test_american_ipad_product_group_links_attributes_to_offers(self):
        group = json.loads((FIXTURES / 'ipad_pro_us_group.json').read_text(encoding='utf-8'))
        html = '<script type="application/ld+json">' + json.dumps(group) + '</script>'
        result = parse_product_page(html, 'https://www.apple.com/shop/buy-ipad/ipad-pro', 'https://www.apple.com')
        self.assertEqual(len(result['variant_prices']), 48)
        self.assertEqual(result['currency'], 'USD')
        self.assertTrue(all(v['part_number'] and v['price'] and v['attributes'] for v in result['variant_prices']))

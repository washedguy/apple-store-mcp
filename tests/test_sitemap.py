import unittest
from apple_store_mcp.shop.search import parse_sitemap
from apple_store_mcp.shop.errors import RetailerError


class SitemapTests(unittest.TestCase):
    def test_main_links_and_whitespace_search(self):
        html = '<nav><a href="/other">MacBook Pro</a></nav><main><a href="/macbook-pro/">MacBook&nbsp;Pro</a><a href="/macbook-pro/">Duplicate</a></main>'
        links = parse_sitemap(html, 'https://www.apple.com', 'macbook pro')
        self.assertEqual(links, [{'title': 'MacBook Pro', 'url': 'https://www.apple.com/macbook-pro/'}])

    def test_invalid_page_is_an_error(self):
        with self.assertRaises(RetailerError):
            parse_sitemap('<html>unexpected page</html>', 'https://www.apple.com')

    def test_search_result_marks_page_type(self):
        import asyncio
        from unittest.mock import patch
        from apple_store_mcp.client import Client
        async def fake_fetch(url, **kwargs):
            self.assertEqual(url, 'https://www.apple.com/sitemap/')
            return '<main><a href="/ipad-pro/">iPad Pro</a></main>', url
        with patch('apple_store_mcp.shop.search.fetch_text', fake_fetch):
            result = asyncio.run(Client('us').search_sitemap('ipad pro'))
        self.assertEqual(result['source'], 'sitemap')
        self.assertEqual(result['products'][0]['type'], 'sitemap')
        self.assertIsNone(result['products'][0]['price'])

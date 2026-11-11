"""Exercise the MCP over a real stdio transport, not in-process calls."""
import asyncio
import sys
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class ProtocolTests(unittest.TestCase):
    def test_stdio_discovery_call_and_error(self):
        async def run():
            params = StdioServerParameters(command=sys.executable, args=['-m', 'apple_store_mcp'],
                                           cwd=Path(__file__).resolve().parents[1])
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertIn('compare_availability', {t.name for t in tools.tools})
                    self.assertIn('check_configuration_delivery', {t.name for t in tools.tools})
                    result = await session.call_tool('list_storefronts', {})
                    self.assertFalse(result.is_error)
                    self.assertTrue(any(x['country'] == 'de' for x in result.structured_content['storefronts']))
                    result = await session.call_tool('search_products', {'query': ' ', 'country': 'de'})
                    self.assertTrue(result.is_error)
                    self.assertEqual(result.structured_content['error']['code'], 'invalid_input')
        asyncio.run(run())

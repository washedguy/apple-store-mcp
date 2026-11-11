import asyncio
import unittest

from apple_store_mcp.server import mcp


class TestMCP(unittest.TestCase):
    def test_tool_discovery(self):
        async def run():
            tools = await mcp.list_tools()
            return [t.name for t in tools]
        names = asyncio.run(run())
        self.assertIn("list_storefronts", names)
        self.assertIn("search_products", names)
        self.assertIn("get_product", names)
        self.assertIn("find_stores", names)

    def test_list_storefronts(self):
        async def run():
            res = await mcp.call_tool("list_storefronts", {})
            return res
        res = asyncio.run(run())
        # structured content should be present
        self.assertTrue(hasattr(res, "structured_content") or hasattr(res, "content"))
        # ensure no error
        if hasattr(res, "is_error"):
            self.assertFalse(res.is_error)


if __name__ == "__main__":
    unittest.main()
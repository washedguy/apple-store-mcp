import asyncio
import unittest

from apple_store_mcp.shop.cache import cached_call


class TestCache(unittest.TestCase):
    def test_cache_hit(self):
        calls = {"n": 0}

        async def fetch():
            calls["n"] += 1
            return {"found": True, "value": calls["n"]}

        async def run():
            r1 = await cached_call("search", ("k",), False, fetch)
            r2 = await cached_call("search", ("k",), False, fetch)
            return r1, r2, calls["n"]

        r1, r2, n = asyncio.run(run())
        self.assertEqual(n, 1)
        self.assertFalse(r1["cache"]["hit"])
        self.assertTrue(r2["cache"]["hit"])

    def test_fresh_bypass(self):
        calls = {"n": 0}

        async def fetch():
            calls["n"] += 1
            return {"found": True, "value": calls["n"]}

        async def run():
            await cached_call("search", ("k2",), False, fetch)
            await cached_call("search", ("k2",), True, fetch)

        asyncio.run(run())
        self.assertEqual(calls["n"], 2)

    def test_missing_product_not_cached(self):
        calls = {"n": 0}

        async def fetch():
            calls["n"] += 1
            return {"found": False, "value": None}

        async def run():
            await cached_call("product", ("k3",), False, fetch)
            await cached_call("product", ("k3",), False, fetch)

        asyncio.run(run())
        self.assertEqual(calls["n"], 2)


if __name__ == "__main__":
    unittest.main()
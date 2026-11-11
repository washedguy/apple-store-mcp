"""Public Apple Store client, composed from focused request modules."""

from .shop import configurator, delivery, fulfillment, products, search as search_api, stores as store_api
from .shop.config import STOREFRONTS, path_prefix, site_prefix, base_url
from .shop.errors import RetailerError as RetailerError


class Client:
    def __init__(self, country: str = "us", language: str | None = None):
        if country not in STOREFRONTS:
            raise ValueError(f"Unsupported country: {country}")
        host, currency, languages = STOREFRONTS[country]
        language = language or languages[0]
        if language not in languages:
            raise ValueError(f"Unsupported language for {country}; choose: {', '.join(languages)}.")
        self.country = country
        self.language = language
        self.currency = currency
        self.host = host
        self.base = base_url(country, language)
        self.prefix = path_prefix(country, language)
        self.site_prefix = site_prefix(country, language)
        self.hosts = {host, host.removeprefix("www.")}
        # for apple.com.cn
        if host.endswith("apple.com.cn"):
            self.hosts.add("apple.com.cn")

    async def search_page(self, query, page=1, tab="explore"):
        return await search_api.search_page(self, query, page, tab)

    async def search(self, query, page=1, tab="explore", brand=None, min_price=None, max_price=None):
        return await search_api.search(self, query, page, tab, brand, min_price, max_price)

    async def search_sitemap(self, query):
        return await search_api.search_sitemap(self, query)

    async def product(self, reference):
        return await products.product(self, reference)

    async def configuration(self, collection, selections):
        return await configurator.configuration(self, collection, selections)

    async def delivery(self, buy_url, parts, postal_code):
        return await delivery.delivery(self, buy_url, parts, postal_code)

    async def fulfillment(self, buy_url, collection, selections, location):
        return await fulfillment.fulfillment(self, buy_url, collection, selections, location)

    async def stores(self, query):
        return await store_api.stores(self, query)

    async def sitemap(self, query=None):
        return await search_api.sitemap(self, query)
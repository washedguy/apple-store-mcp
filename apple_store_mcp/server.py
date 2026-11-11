"""MCP tools for the Apple Store."""
from typing import Annotated, Literal

from .mcp_api.server import StructuredMCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field
from .mcp_api.schemas import AllStoresResult, BrowseResult, ComparisonResult, ConfigurationDeliveryEstimates, ProductInformation, ConfigurationResult, DeliveryEstimates, VariantPickupResult, FulfillmentResult, ProductResult, SearchResult, SitemapResult, StorefrontList, StoreResult

from .client import Client, RetailerError
from .shop.config import STOREFRONTS
from .shop.cache import cached_call
from .shop.browse import browse
from .shop.product_info import product_info
from .shop.comparison import compare
from .shop.fulfillment import variant_pickup
from .shop.stores import list_all

mcp = StructuredMCPServer("apple-store", instructions=(
    "Search the Apple Store. Use list_storefronts to discover supported countries and shop languages. "
    "Use search_products for sitemap discovery; select apple_search and the accessories tab for priced accessory results. "
    "Use product_information to compare products, option prices and requirements, and optionally availability. Use get_product for product details. Use get_configuration_options for current price and compatible choices; use get_configuration_pickup to check those selections near a location. Use compare_availability to compare variant pickup and delivery across locations, including all stores in smaller countries. Use check_delivery for part numbers or check_configuration_delivery for configured products and a postal code. These tools only read information. Use find_stores to find Apple retail stores. "
    "Prices and availability can change; availability is not a reservation or exact stock count."
))

Country = Annotated[str, Field(description="Storefront country code, e.g. us, de, fr, ch, be. Use list_storefronts for supported values.")]
Language = Annotated[str | None, Field(description="Shop language; defaults to the country's main language. Switzerland: de/fr; Belgium: fr/nl; Canada: en/fr.")]


def _client(country, language):
    try:
        return Client(country, language)
    except ValueError as exc:
        raise ToolError(f"[invalid_input] {exc}") from exc


Query = Annotated[str, Field(min_length=1, max_length=200, description="Product keywords, model number, or part number. Local-language terms may work best.")]

Tab = Annotated[Literal["explore", "accessories", "support", "retail"], Field(description="Search tab. 'accessories' returns buyable products with prices; 'explore' returns curated and content results.")]


@mcp.tool(structured_output=True)
async def list_storefronts() -> StorefrontList:
    """List supported Apple Store countries, shop languages, currencies and URLs. Product and store IDs are country-specific."""
    shops = []
    for country, (host, currency, languages) in STOREFRONTS.items():
        shops.append({"country": country, "retailer": "apple", "languages": list(languages), "default_language": languages[0],
                      "currency": currency, "url": f"https://{host}", "delivery_filter_languages": []})
    return StorefrontList.model_validate({"storefronts": shops})


@mcp.tool(structured_output=True)
async def search_products(
    query: Query,
    country: Country = "us",
    language: Language = None,
    tab: Tab = "explore",
    page: Annotated[int, Field(ge=1, le=30, description="Results page, starting at 1. Use next_page to continue.")] = 1,
    brand: Annotated[str | None, Field(min_length=1, max_length=100, description="Filter by brand (applied locally).")] = None,
    min_price: Annotated[float | None, Field(ge=0, description="Minimum price in the local currency (applied locally).")] = None,
    max_price: Annotated[float | None, Field(ge=0, description="Maximum price in the local currency (applied locally).")] = None,
    fresh: Annotated[bool, Field(description="Bypass the process cache and request current shop data.")] = False,
    source: Annotated[Literal["sitemap", "apple_search"], Field(description="Sitemap page discovery or Apple search results. Sitemap does not contain individual product prices or variants.")] = "sitemap",
) -> SearchResult:
    """Find sitemap pages by default; use apple_search for Apple search tabs and priced accessories. Sitemap results are not a complete product catalog and do not have variant prices. Apple search filters apply locally to one page."""
    if not query.strip():
        raise ToolError("[invalid_input] query must not be blank")
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ToolError("[invalid_input] min_price must not exceed max_price")
    if source == "sitemap" and (page != 1 or brand or min_price is not None or max_price is not None):
        raise ToolError("[invalid_input] Sitemap discovery has no pagination, brand, or price filters; use source=apple_search for those.")
    try:
        client = _client(country, language)
        search_args = (query.strip(), page, tab)
        result = await cached_call("search", (country, language, source, *search_args), fresh,
                                   lambda: client.search_sitemap(query.strip()) if source == "sitemap" else client.search(*search_args))
        # apply local filters
        products = result["products"]
        if brand:
            products = [p for p in products if p.get("brand") and p["brand"].casefold() == brand.casefold()]
        if min_price is not None or max_price is not None:
            lo = min_price if min_price is not None else 0
            hi = max_price if max_price is not None else float("inf")
            products = [p for p in products if isinstance(p.get("price"), (int, float)) and lo <= p["price"] <= hi]
        result["products"] = products
        result["count"] = len(products)
        if brand or min_price is not None or max_price is not None:
            result["local_filters"] = []
            if brand:
                result["local_filters"].append(f"brand:{brand}")
            if min_price is not None or max_price is not None:
                result["local_filters"].append(f"price:{min_price}-{max_price}")
            result["note"] = (result.get("note") or "") + " Brand and price filters applied locally to the returned page."
        # currency fallback
        for p in result["products"]:
            if result.get("source") != "sitemap" and p.get("price") is not None and p.get("currency") is None:
                p["currency"] = client.currency
        if source == "apple_search":
            result["tab"] = tab
        return SearchResult.model_validate(result)
    except RetailerError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc


@mcp.tool(structured_output=True)
async def get_product(
    reference: Annotated[str, Field(min_length=1, max_length=500, description="Product part number, slug (e.g. iphone-17), or HTTPS Apple Store product URL.")],
    country: Country = "us",
    language: Language = None,
    fresh: Annotated[bool, Field(description="Bypass the process cache and request current shop data.")] = False,
) -> ProductResult:
    """Read product details from an Apple Store product page by part number, slug, or URL, including price, availability, description, images and specifications where available."""
    if not reference.strip():
        raise ToolError("[invalid_input] reference must not be blank")
    try:
        client = _client(country, language)
        result = await cached_call("product", (country, language, reference.strip()), fresh,
                                   lambda: client.product(reference.strip()))
        return ProductResult.model_validate(result)
    except RetailerError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc


@mcp.tool(structured_output=True)
async def product_information(
    product: Annotated[str, Field(min_length=1, max_length=500, description="Product name or Apple product page URL, for example MacBook Pro PROLED XDR.")],
    country: Country = "us",
    language: Language = None,
    options: Annotated[dict[str, str] | None, Field(description="Optional product attributes to narrow the results, such as memory or color.")] = None,
    location: Annotated[str | None, Field(max_length=150, description="Optional city or postal code for nearby store availability.")] = None,
    postal_code: Annotated[str | None, Field(max_length=32, description="Optional delivery postal code.")] = None,
) -> ProductInformation:
    """Compare product variants, prices and option requirements. Requirements and upgrade prices are scoped to the stated example, not inferred for all combinations. Availability is checked only for identified variants or a clearly described configuration. No purchases or reservations."""
    try:
        return ProductInformation.model_validate(await product_info(_client(country, language), product, options, location, postal_code))
    except RetailerError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc


@mcp.tool(structured_output=True)
async def explore_product(
    url: Annotated[str, Field(description="Apple product page or buy link returned by search or a previous call.")],
    country: Country = "us",
    language: Language = None,
    options: Annotated[dict[str, str] | None, Field(description="Optional choices, e.g. {\"memory\": \"48 GB\"}. To preserve a previous configuration, pass its selection object with the desired changes.")] = None,
    location: Annotated[str | None, Field(max_length=150, description="Optional city or postal code to check nearby store availability.")] = None,
    postal_code: Annotated[str | None, Field(max_length=32, description="Optional delivery postal code.")] = None,
) -> BrowseResult:
    """Explore product choices, variants and prices; add a location for nearby store quotes or postal_code for delivery estimates. Read-only; no reservation or purchase."""
    try:
        return BrowseResult.model_validate(await browse(_client(country, language), url, options, location, postal_code))
    except RetailerError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc


@mcp.tool(structured_output=True)
async def get_configuration_options(
    collection: Annotated[str, Field(min_length=1, max_length=120, description="Apple configurator collection identifier from a buy page, e.g. MBP_2026_COLLECTION.")],
    selections: Annotated[dict[str, str], Field(description="Apple dimension identifiers and selected values. Use returned dimension names and values to refine selections; availability depends on the product.")],
    country: Country = "us",
    language: Language = None,
) -> ConfigurationResult:
    """Get live configuration choices and relative price deltas. Upgrade choices may require changing other dimensions; they are not necessarily compatible. The selected price and deltas come from Apple and depend on the returned selected dimensions. Identifiers and coverage vary by product and storefront."""
    try:
        return ConfigurationResult.model_validate(await _client(country, language).configuration(collection, selections))
    except RetailerError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc


@mcp.tool(structured_output=True)
async def check_delivery(
    buy_url: Annotated[str, Field(description="Apple buy-page URL for the selected storefront.")],
    part_numbers: Annotated[list[str], Field(min_length=1, max_length=20, description="Product part numbers returned by get_product.")],
    postal_code: Annotated[str, Field(min_length=1, max_length=32, description="Delivery postal code.")],
    country: Country = "us",
    language: Language = None,
) -> DeliveryEstimates:
    """Read current delivery estimates for product variants and a postal code. No purchase or reservation is made. A missing estimate means unknown, not unavailable."""
    try:
        return DeliveryEstimates.model_validate(await _client(country, language).delivery(buy_url, part_numbers, postal_code))
    except RetailerError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc


@mcp.tool(structured_output=True)
async def check_configuration_delivery(
    buy_url: Annotated[str, Field(description="Apple buy-page URL for the selected storefront.")],
    collection: Annotated[str, Field(description="Configurator collection identifier.")],
    selections: Annotated[dict[str, str], Field(description="Selected configuration dimensions and values.")],
    postal_code: Annotated[str, Field(min_length=1, max_length=32, description="Delivery postal code.")],
    country: Country = "us",
    language: Language = None,
) -> ConfigurationDeliveryEstimates:
    """Check delivery estimates for a configurable product. The returned configuration identifies the checked selections. No purchase or reservation is made; a missing estimate is unknown."""
    try:
        return ConfigurationDeliveryEstimates.model_validate(await _client(country, language).configuration_delivery(buy_url, collection, selections, postal_code))
    except RetailerError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc


@mcp.tool(structured_output=True)
async def get_configuration_pickup(
    buy_url: Annotated[str, Field(description="Apple buy-page URL in the selected storefront.")],
    location: Annotated[str, Field(min_length=1, max_length=150, description="City or postal code near the desired Apple stores.")],
    collection: Annotated[str, Field(description="Configurator collection identifier from the buy page.")],
    selections: Annotated[dict[str, str], Field(description="Selected configuration dimension identifiers and values.")],
    country: Country = "us",
    language: Language = None,
) -> FulfillmentResult:
    """Check price, options and nearby store availability for a configuration. Read-only: does not reserve or purchase anything. The returned configuration identifies the checked product. Apple may block or change the endpoint."""
    try:
        return FulfillmentResult.model_validate(await _client(country, language).fulfillment(buy_url, collection, selections, location))
    except RetailerError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc


@mcp.tool(structured_output=True)
async def browse_sitemap(
    query: Annotated[str | None, Field(default=None, max_length=100, description="Optional filter for link text or URL.")] = None,
    country: Country = "us",
    language: Language = None,
    fresh: Annotated[bool, Field(description="Bypass the process cache and request current shop data.")] = False,
) -> SitemapResult:
    """Browse the Apple Store sitemap for a country and return links, optionally filtered by a keyword. Useful for discovering product pages when search is unavailable."""
    try:
        client = _client(country, language)
        result = await cached_call("search", ("sitemap", country, language, query), fresh,
                                   lambda: client.sitemap(query))
        return SitemapResult.model_validate(result)
    except RetailerError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc


@mcp.tool(structured_output=True)
async def compare_availability(
    buy_url: Annotated[str, Field(description="Apple buy-page URL for the selected storefront.")],
    part_numbers: Annotated[list[str], Field(min_length=1, max_length=20, description="Part numbers to compare.")],
    country: Country = "us",
    language: Language = None,
    pickup_locations: Annotated[list[str] | None, Field(description="Cities or postal codes to search for nearby stores.")] = None,
    delivery_postcodes: Annotated[list[str] | None, Field(description="Postcodes to check for delivery estimates.")] = None,
    all_stores: Annotated[bool, Field(description="Check the country directory and attempt every listed store; limited to countries with at most 30 stores.")] = False,
) -> ComparisonResult:
    """Compare pickup and delivery estimates for variants. Failed, missing and unchecked results are reported as unknown. Read-only; does not reserve or purchase."""
    try:
        return ComparisonResult.model_validate(await compare(_client(country, language), buy_url, part_numbers, pickup_locations or [], delivery_postcodes or [], all_stores))
    except RetailerError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc


@mcp.tool(structured_output=True)
async def list_apple_stores(country: Country = "us", language: Language = None) -> AllStoresResult:
    """List Apple retail stores published in the selected country's store directory."""
    try:
        return AllStoresResult.model_validate(await list_all(_client(country, language)))
    except RetailerError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc


@mcp.tool(structured_output=True)
async def check_variant_pickup(
    buy_url: Annotated[str, Field(description="Apple buy-page URL for the selected storefront.")],
    part_numbers: Annotated[list[str], Field(min_length=1, max_length=20, description="Variant part numbers returned by explore_product or get_product.")],
    location: Annotated[str, Field(min_length=1, max_length=150, description="City or postal code to find nearby stores.")],
    country: Country = "us",
    language: Language = None,
) -> VariantPickupResult:
    """Read pickup availability quotes for product variants at nearby stores. Results are estimates, not reservations or stock counts."""
    try:
        return VariantPickupResult.model_validate(await variant_pickup(_client(country, language), buy_url, part_numbers, location))
    except RetailerError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc


@mcp.tool(structured_output=True)
async def find_stores(
    query: Annotated[str, Field(min_length=1, max_length=100, description="City, region, or store name in the selected country.")],
    country: Country = "us",
    language: Language = None,
    fresh: Annotated[bool, Field(description="Bypass the process cache and request current shop data.")] = False,
) -> StoreResult:
    """Find Apple retail stores in the selected country. Returns store names, addresses, phone numbers and coordinates where available."""
    if not query.strip():
        raise ToolError("[invalid_input] query must not be blank")
    try:
        client = _client(country, language)
        result = await cached_call("stores", (country, language, query.strip()), fresh,
                                   lambda: client.stores(query.strip()))
        return StoreResult.model_validate(result)
    except RetailerError as exc:
        raise ToolError(f"[{exc.code}] {exc}") from exc


def main():
    from .cli import main as cli_main
    cli_main()


if __name__ == "__main__":
    main()

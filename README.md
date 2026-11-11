# Apple Store MCP

A read-only MCP server for browsing Apple Store products, configurations, prices, delivery estimates and store pickup. It uses HTTP requests and does not require an Apple account or browser. It cannot place orders or reserve products.

## Install

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Add this server to your MCP client's configuration:

```json
{
  "mcpServers": {
    "apple-store": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/washedguy/apple-store-mcp.git",
        "apple-store-mcp"
      ]
    }
  }
}
```

Restart your MCP client. The location of this configuration depends on the client. `uvx` downloads and runs the server; no checkout is needed. If your client cannot find `uvx`, use the absolute path shown by `which uvx` (macOS/Linux) or `where uvx` (Windows).

## Use it

Ask your MCP client questions such as:

- “Find the iPhone Duo in Germany and show its colors and storage prices.”
- “What are the delivery estimates for these variants to postcode 60313?”
- “Which Apple Stores near Frankfurt have this model available for pickup?”
- “Show MacBook Pro options and the price with 48 GB of memory.”

Use `list_storefronts` to see the supported countries and languages. Prices, delivery estimates and pickup availability are specific to the selected storefront and can change. A delivery estimate or pickup quote is not a reservation or exact inventory count.

### How the tools work together

1. `search_products` finds product pages. By default it uses Apple's sitemap, which is useful for discovery but is not a complete catalog of individual products.
2. `product_information` accepts a product name or Apple URL and returns grouped options, variant prices and observed compatibility requirements. `explore_product` follows product pages and exposes additional configuration details. `get_product` also returns available product details and part numbers.
3. Add `location` to `explore_product` for nearby store quotes and `postal_code` for delivery estimates. For a configurable product, pass its returned `selection` back as `options` when changing a choice to preserve the rest of the configuration. If a check fails, product data is retained and the failure appears in `issues`.
4. Alternatively, use `check_delivery` and `check_variant_pickup` with part numbers, or `list_apple_stores` to browse a country's store directory.

Use `compare_availability` to check several pickup locations and delivery postcodes together. Set `all_stores: true` to attempt all stores in a country with at most 30 Apple Stores. The response identifies failed checks, missing stores, missing variant quotes and unknown statuses; `complete` refers to the requested checks, not every possible postcode or retailer. Each store and delivery result carries its own observation time. All-store checks may take a minute or longer.

For example, call `product_information` with `{"product": "MacBook Pro PROLED XDR", "country": "de"}`. Its `options` groups contain entries such as `{"name": "48 GB", "price": {"amount": 660, "currency": "EUR", "kind": "change_from_example"}, "requirements": [...]}`. A `starting_at` price is the lowest observed base-configuration price for that choice. A `change_from_example` price is relative to `example_1`, not the total price. Each requirement identifies the example to which it applies; the examples are sampled configurations, not a complete compatibility matrix. A null price or empty requirements list means the server did not establish one.

For a discrete product, `{"product": "iPad mini", "country": "de", "location": "Frankfurt am Main", "postal_code": "60313"}` returns the listed variants, grouped options and prices, nearby pickup quotes and delivery estimates. Requirements marked `observed_with` describe combinations in the returned variants; they are not proof of every possible combination. Filter with `options`, for example `{"storage": "256 GB", "color": "Mitternacht"}`.

The lower-level `get_configuration_options`, `get_configuration_pickup` and `check_configuration_delivery` tools accept Apple's collection and dimension identifiers. `browse_sitemap` and `find_stores` provide additional discovery options. The server is read-only.

## Limitations

- Apple’s interfaces are unofficial and may change or block requests. Coverage varies by product and country; unknown or missing data does not mean an item is unavailable.
- The server has been live-tested with German, US, UK, Japanese, Swiss French, Belgian Dutch and French-Canadian product pages; this is not a guarantee for every product, carrier or storefront. Some carrier-specific details may not be represented.
- An HTTP 541 response is reported as blocked; its precise cause is not inferred. Failed checks are not reported as out of stock.
- The sitemap does not list every variant. Apple search is available with `source: apple_search`; its accessories tab can include purchasable products and prices.
- Delivery estimates are supported for discrete part numbers and supported configurable kits. Configurable-kit delivery was verified with a German MacBook Pro; coverage for other products and storefronts is not yet established. Comparing delivery across postcodes requires choosing those postcodes.
- Configurator prices can be starting prices. Option price changes depend on the selected configuration; upgrades may require changing other choices.
- Search, product and store results use short process-local caches. Use `fresh: true` where available to bypass them.

## Development

```bash
git clone https://github.com/washedguy/apple-store-mcp.git
cd apple-store-mcp
uv sync
uv run ruff check apple_store_mcp tests
uv run python -m unittest discover -s tests -v
uv build
```

Run `uv run apple-store-mcp` to start the stdio server, or `uv run python -m apple_store_mcp --config` to print a local client configuration. `uv run python -m apple_store_mcp --check de` runs a live diagnostic; Apple can block or rate-limit requests. Optional proxies use the standard `HTTPS_PROXY` environment variable; see [.env.example](.env.example).

CI runs offline fixtures and a real stdio MCP client test. Maintainers can optionally run the live Germany diagnostic through the GitHub Actions workflow's manual `live_check` input; a live failure may reflect Apple blocking the runner.

Unofficial project, not affiliated with Apple. Licensed under the [MIT License](LICENSE).

# apple-store-mcp

MCP server for Apple Store products, configurations, prices, and availability.

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

## Tools

| Tool | What it does |
| --- | --- |
| `list_storefronts` | List supported storefronts. |
| `search_products`, `browse_sitemap` | Find products and browse Apple's sitemap. |
| `get_product`, `product_information`, `explore_product` | Get product details, options, and prices. |
| `get_configuration_options` | Get configurable product options. |
| `list_apple_stores`, `find_stores` | List or find stores. |
| `check_delivery`, `check_configuration_delivery` | Check delivery estimates. |
| `check_variant_pickup`, `get_configuration_pickup` | Check pickup availability. |
| `compare_availability` | Compare pickup and delivery across locations. |

## Notes

- Product and storefront coverage varies. Missing data does not mean an item is unavailable.
- Prices and availability can change. Configurator prices can depend on other selected options.
- Set `fresh: true` where available to bypass the local cache. Set `HTTPS_PROXY` to use a proxy.
- This is an unofficial integration and Apple's interfaces may change.

## Development

```bash
git clone https://github.com/washedguy/apple-store-mcp.git
cd apple-store-mcp
uv sync
uv run ruff check apple_store_mcp tests
uv run python -m unittest discover -s tests -v
uv build
```

## Author

**[washed.dev](https://washed.dev)** · Building websites and web apps for your business

## License

[MIT](LICENSE)

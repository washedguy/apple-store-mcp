"""Retrieve Apple Store product pages."""
import re
from urllib.parse import urljoin, urlsplit

from .errors import RetailerError
from .http import fetch_text
from .parsing import parse_product_page, _ld_json_products, parse_variant_prices, parse_options, parse_catalog_variants


APPLE_HOSTS = {"www.apple.com", "apple.com", "www.apple.com.cn", "apple.com.cn"}


def _candidate_urls(self, reference):
    reference = reference.strip()
    if "://" in reference:
        return [reference]
    ref = reference.strip("/")
    candidates = []
    if reference.startswith("/"):
        candidates.append(f"{self.base}{reference}")
    else:
        prefixes = []
        if getattr(self, "site_prefix", None):
            prefixes.append(self.site_prefix)
        if getattr(self, "prefix", None) and self.prefix not in prefixes:
            prefixes.append(self.prefix)
        # marketing pages: /<site_prefix>/<ref>/
        for pref in prefixes:
            candidates.append(f"{self.base}/{pref}/{ref}/")
            candidates.append(f"{self.base}/{pref}/{ref}")
        # buy pages: /<prefix>/shop/buy-*/<ref>
        buy_prefixes = [self.prefix] if getattr(self, "prefix", None) else []
        if self.site_prefix and self.site_prefix not in buy_prefixes:
            buy_prefixes.append(self.site_prefix)
        for pref in buy_prefixes:
            for buy in ("buy-iphone", "buy-mac", "buy-ipad", "buy-watch", "buy-airpods", "buy-apple-tv"):
                candidates.append(f"{self.base}/{pref}/shop/{buy}/{ref}")
                candidates.append(f"{self.base}/{pref}/shop/{buy}/{ref}/")
        # shop product pages: /<prefix>/shop/product/<ref>/ (search-style prefix)
        shop_prefixes = [self.prefix] if getattr(self, "prefix", None) else []
        if self.site_prefix and self.site_prefix not in shop_prefixes:
            shop_prefixes.append(self.site_prefix)
        for pref in shop_prefixes:
            candidates.append(f"{self.base}/{pref}/shop/product/{ref}/")
            candidates.append(f"{self.base}/{pref}/shop/product/{ref}")
        # generic (US root)
        candidates.append(f"{self.base}/{ref}/")
        candidates.append(f"{self.base}/{ref}")
        candidates.append(f"{self.base}/shop/product/{ref}/")
        candidates.append(f"{self.base}/shop/product/{ref}")
    # deduplicate preserving order
    seen = set()
    out = []
    for u in candidates:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


async def product(self, reference):
    reference = reference.strip()
    last_error = None
    parse_failure = None
    for url in _candidate_urls(self, reference):
        try:
            parts = urlsplit(url)
        except ValueError as exc:
            raise RetailerError("Invalid product URL.", code="invalid_input") from exc
        host = parts.hostname
        if parts.scheme != "https" or host not in APPLE_HOSTS or parts.username is not None or parts.port is not None:
            raise RetailerError("Use an HTTPS Apple Store product URL or a valid product path.", code="invalid_input")
        try:
            html, final_url = await fetch_text(url)
        except RetailerError as exc:
            if exc.code == "not_found":
                last_error = exc
                continue
            raise
        if "sitemap" in final_url:
            raise RetailerError("Apple redirected the request to the sitemap (possible rate limiting).", code="blocked")
        try:
            details = parse_product_page(html, final_url, self.base)
            details["variant_prices"] = details["variant_prices"] or parse_catalog_variants(html) or parse_variant_prices(html)
            details["options"] = parse_options(html)
            collections = list(dict.fromkeys(re.findall(r"collection=([A-Z0-9_]+_COLLECTION)", html)))
            details["configuration_collections"] = collections
        except RetailerError as exc:
            parse_failure = exc
            continue
        # If no price, try buy link from ld+json potentialAction
        if details.get("price") is None:
            ld = _ld_json_products(html)
            buy_url = None
            if ld:
                pa = ld[0].get("potentialAction") or {}
                urls = pa.get("url") or []
                if isinstance(urls, str):
                    urls = [urls]
                if urls:
                    buy_url = urls[0]
            if buy_url:
                try:
                    buy_full = buy_url if buy_url.startswith("http") else urljoin(self.base, buy_url)
                    buy_html, buy_final = await fetch_text(buy_full)
                    buy_details = parse_product_page(buy_html, buy_final, self.base)
                    buy_details["variant_prices"] = buy_details["variant_prices"] or parse_catalog_variants(buy_html) or parse_variant_prices(buy_html)
                    buy_details["options"] = parse_options(buy_html)
                    collections = list(dict.fromkeys(re.findall(r"collection=([A-Z0-9_]+_COLLECTION)", buy_html)))
                    if collections:
                        details["configuration_collections"] = collections
                    if buy_details.get("price") is not None:
                        details["price"] = buy_details["price"]
                        details["currency"] = buy_details.get("currency") or details["currency"]
                        details["resolved_url"] = buy_final
                    if buy_details.get("delivery", {}).get("status") not in (None, "unknown"):
                        details["delivery"] = buy_details["delivery"]
                        details["preorder"] = buy_details["preorder"]
                        details["is_preorder"] = buy_details["is_preorder"]
                    if buy_details.get("variant_prices"):
                        details["variant_prices"] = buy_details["variant_prices"]
                    if buy_details.get("options"):
                        details["options"] = buy_details["options"]
                except RetailerError:
                    pass
        if details.get("currency") is None:
            details["currency"] = self.currency
        if not details.get("id"):
            details["id"] = reference
        result = {
            "retailer": "apple",
            "country": self.country,
            "language": self.language,
            "reference": reference,
            "found": True,
            "product": details,
            "reason": None,
        }
        return result
    # none found
    if parse_failure is not None:
        raise parse_failure
    if last_error is not None:
        return {"retailer": "apple", "country": self.country, "language": self.language, "reference": reference, "found": False, "product": None, "reason": "product_url_not_found"}
    raise RetailerError("Could not retrieve product page.")
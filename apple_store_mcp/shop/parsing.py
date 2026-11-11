"""Parse Apple Store pages."""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .errors import RetailerError


def _extract_search_data(html: str) -> dict:
    marker = "window.pageLevelData.searchResults.searchData = "
    if marker not in html:
        raise RetailerError("Search page did not contain product data; the retailer may have changed the page.")
    raw = html.split(marker, 1)[1]
    # find terminating semicolon at top level
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RetailerError("Could not parse the retailer search data.") from exc
    return obj


def _image_url_from_product_images(product_images) -> str | None:
    try:
        items = product_images.get("items") if isinstance(product_images, dict) else None
        if not items:
            return None
        val = items[0].get("value", {}) if isinstance(items[0], dict) else {}
        sources = val.get("sources") or []
        if sources:
            return sources[0].get("srcSet")
    except Exception:
        return None
    return None


def parse_search(html: str, base: str, country: str, language: str, query: str, tab: str, page: int) -> dict:
    data = _extract_search_data(html)
    selected_tab = data.get("selectedTab") or tab
    current_page = data.get("pageNumber") or page
    num_pages = data.get("numOfPages")
    next_link = data.get("nextLink")
    has_next = bool(data.get("hasNextResults"))
    total_text = data.get("totalCountText")

    products = []

    if selected_tab == "accessories" or tab == "accessories":
        section = (data.get("results") or {}).get("accessories", {})
        inner = section.get("accessories", section) if isinstance(section, dict) else section
        tiles = (inner.get("tiles") or {}).get("items") or [] if isinstance(inner, dict) else []
        for tile in tiles:
            val = tile.get("value", {}) if isinstance(tile, dict) else {}
            link = val.get("link") or {}
            url = link.get("url")
            full_url = urljoin(base, url) if url else None
            price_info = val.get("productPrice") or {}
            price = None
            price_str = price_info.get("priceCurrent")
            if isinstance(price_str, str):
                # Keep digits, commas and dots; determine decimal separator.
                cleaned = re.sub(r"[^0-9.,]", "", price_str)
                if cleaned:
                    if "," in cleaned and "." in cleaned:
                        if cleaned.rfind(",") > cleaned.rfind("."):
                            cleaned = cleaned.replace(".", "").replace(",", ".")
                        else:
                            cleaned = cleaned.replace(",", "")
                    elif "," in cleaned:
                        cleaned = cleaned.replace(",", ".")
                    try:
                        price = float(cleaned) if cleaned else None
                    except ValueError:
                        price = None
            products.append({
                "id": val.get("partNumber") or val.get("basePartNumber"),
                "title": val.get("title"),
                "brand": None,
                "price": price,
                "currency": price_info.get("priceCurrency") or None,
                "url": full_url,
                "image": _image_url_from_product_images(val.get("productImages")),
                "delivery": {"status": "unknown", "retailer_status": None, "retailer_code": None, "earliest": None, "preorder": False, "is_preorder": False},
                "preorder": False,
                "is_preorder": False,
            })
    else:
        # explore tab: curated tiles + organic results
        section = (data.get("results") or {}).get("explore", {})
        # curated
        curated = (section.get("exploreCurated") or {}).get("tiles", {}).get("items") or []
        for tile in curated:
            val = tile.get("value", {}) if isinstance(tile, dict) else {}
            products.append({
                "id": None,
                "title": val.get("title"),
                "brand": "Apple",
                "price": None,
                "currency": None,
                "url": urljoin(base, (val.get("navLinks") or [{}])[0].get("url") or "") if val.get("navLinks") else None,
                "description": val.get("description"),
                "type": "curated",
                "delivery": {"status": "unknown", "retailer_status": None, "retailer_code": None, "earliest": None, "preorder": False, "is_preorder": False},
                "preorder": False,
                "is_preorder": False,
            })
        organic = (section.get("exploreOrganic") or {}).get("tiles", {}).get("items") or []
        for tile in organic:
            val = tile.get("value", {}) if isinstance(tile, dict) else {}
            link = val.get("link") or {}
            products.append({
                "id": None,
                "title": val.get("title"),
                "brand": None,
                "price": None,
                "currency": None,
                "url": urljoin(base, link["url"]) if link.get("url") else None,
                "description": val.get("description"),
                "type": "organic",
                "delivery": {"status": "unknown", "retailer_status": None, "retailer_code": None, "earliest": None, "preorder": False, "is_preorder": False},
                "preorder": False,
                "is_preorder": False,
            })

    # determine next page
    next_page = None
    if has_next:
        # use nextLink page param
        try:
            q = urlsplit(next_link).query
            import urllib.parse
            params = dict(urllib.parse.parse_qsl(q))
            np = params.get("page")
            next_page = int(np) if np else current_page + 1
        except (ValueError, TypeError):
            next_page = current_page + 1
    if not has_next:
        next_page = None

    # currency fallback from data metrics? search data may have no currency; set later by caller? We'll leave None.
    return {
        "query": query,
        "products": products,
        "count": len(products),
        "total_products": None,
        "page": current_page,
        "next_page": next_page,
        "paging": {"current_page": current_page, "page_count": num_pages, "max_page": num_pages},
        "source": "search_page",
        "coverage": "search_page",
        "tab": selected_tab,
        "total_text": total_text,
        "note": "Apple search returns curated and content results; the 'accessories' tab contains buyable products with prices. total_text is the shop's count, not a verified match count.",
    }


def _ld_json_products(html: str) -> list[dict]:
    out = []
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            obj = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and obj.get("@type") in ("Product", "ProductGroup"):
            out.append(obj)
        if isinstance(obj, list):
            for o in obj:
                if isinstance(o, dict) and o.get("@type") in ("Product", "ProductGroup"):
                    out.append(o)
    return out


def parse_product_page(html: str, url: str, base: str) -> dict:
    products = _ld_json_products(html)
    if not products:
        raise RetailerError("The page did not contain product data; the retailer may have changed the page.")
    p = products[0]
    group_variants = []
    if p.get("@type") == "ProductGroup":
        for variant in p.get("hasVariant") or []:
            if not isinstance(variant, dict):
                continue
            offer = variant.get("offers") or {}
            if not isinstance(offer, dict):
                continue
            amount = offer.get("price")
            try:
                amount = float(amount) if amount is not None else None
            except (TypeError, ValueError):
                amount = None
            attributes = {str(a.get("name") or a.get("propertyID")): str(a["value"])
                          for a in variant.get("additionalProperty") or []
                          if isinstance(a, dict) and (a.get("name") or a.get("propertyID")) and a.get("value") is not None}
            group_variants.append({"part_number": variant.get("sku") or offer.get("sku"),
                                   "name": variant.get("name"), "price": amount,
                                   "currency": offer.get("priceCurrency"), "url": offer.get("url"),
                                   "attributes": attributes})
    offers = p.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = offers.get("price")
    if price is None:
        price = offers.get("lowPrice")
    try:
        price = float(price) if price is not None else None
    except (ValueError, TypeError):
        price = None
    currency = offers.get("priceCurrency")
    if group_variants:
        priced = [v for v in group_variants if v["price"] is not None]
        currencies = {v["currency"] for v in priced}
        if priced and len(currencies) == 1:
            price = min(v["price"] for v in priced)
            currency = priced[0]["currency"]
    availability = offers.get("availability")
    status = "unknown"
    if isinstance(availability, str):
        if "InStock" in availability:
            status = "available"
        elif "OutOfStock" in availability:
            status = "unavailable"
        elif "PreOrder" in availability or "Preorder" in availability:
            status = "preorder"
    preorder = status == "preorder"
    sku = offers.get("sku") or p.get("sku")
    image = p.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    images = [{"url": image, "alt": p.get("name")}] if image else []
    delivery = {"status": status, "retailer_status": availability, "retailer_code": None, "earliest": None,
                "preorder": preorder, "is_preorder": preorder}
    details = {
        "id": sku,
        "title": p.get("name"),
        "brand": (p.get("brand") or {}).get("name") if isinstance(p.get("brand"), dict) else p.get("brand"),
        "price": price,
        "currency": currency,
        "url": p.get("url") or url,
        "resolved_url": url,
        "delivery": delivery,
        "preorder": preorder,
        "is_preorder": preorder,
        "ean": None,
        "variants": [],
        "marketplace_offers": [],
        "offers_coverage": "ld_json",
        "description": p.get("description"),
        "description_marketing": None,
        "images": images,
        "rating": {"average": None, "count": None, "scale": None},
        "categories": [],
        "features": [],
        "variant_prices": group_variants,
        "options": None,
    }
    return details


def parse_store_list(html: str, base: str, country: str, language: str) -> list[dict]:
    """Parse Apple store list page into (region, name, url) entries."""

    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.region = None
            self.entries = []
            self._current_text = []
            self._in_heading = False
            self._heading_tag = None

        def handle_starttag(self, tag, attrs):
            if tag in ("h2", "h3"):
                self._in_heading = True
                self._heading_tag = tag
                self._current_text = []
            elif tag == "a":
                href = dict(attrs).get("href") or ""
                # store links look like /retail/slug/ or /de/retail/slug/
                if dict(attrs).get("data-store-number") and re.fullmatch(r"(?:/[a-z-]+)*/retail/[a-z0-9-]+/?", href):
                    # capture text via handle_data
                    self._pending_href = href
                    self._pending_id = dict(attrs)["data-store-number"]

        def handle_data(self, data):
            if self._in_heading:
                self._current_text.append(data)
            if hasattr(self, "_pending_href"):
                txt = data.strip()
                if txt:
                    self.entries.append((self.region, txt, self._pending_href, self._pending_id))
                    del self._pending_href

        def handle_endtag(self, tag):
            if tag in ("h2", "h3") and self._in_heading:
                self.region = " ".join("".join(self._current_text).split())
                self._in_heading = False

    parser = Parser()
    parser.feed(html)
    # deduplicate
    seen = set()
    out = []
    for region, name, href, store_id in parser.entries:
        key = (region, name, href)
        if key in seen:
            continue
        seen.add(key)
        out.append({"id": store_id, "region": region, "name": name, "url": urljoin(base, href)})
    return out


def parse_store_page(html: str) -> dict:
    """Parse an Apple retail store page JSON-LD LocalBusiness."""
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            obj = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and obj.get("@type") == "LocalBusiness":
            addr = obj.get("address") or {}
            geo = obj.get("geo") or {}
            return {
                "id": obj.get("branchCode"),
                "name": obj.get("name"),
                "address": {
                    "street": addr.get("streetAddress"),
                    "house_number": None,
                    "postal_code": addr.get("postalCode"),
                    "city": addr.get("addressLocality"),
                    "country": None,
                },
                "position": {"latitude": geo.get("latitude"), "longitude": geo.get("longitude")},
                "phone": obj.get("telephone"),
            }
    raise RetailerError("Store page did not contain store data.")


COLOR_MAP = {
    "spaceblack": "Space Black", "silver": "Silver", "midnight": "Midnight",
    "starlight": "Starlight", "gold": "Gold", "blue": "Blue", "pink": "Pink",
    "natural": "Natural Titanium", "desert": "Desert Titanium", "black": "Black",
    "white": "White",
}
CHIP_MAP = {"m5max": "M5 Max", "m5pro": "M5 Pro", "m6": "M6", "m5": "M5", "m4": "M4", "m4max": "M4 Max", "m4pro": "M4 Pro"}


def _decode_mac_slug(slug: str) -> dict:
    parts = slug.split("-")
    size_raw = parts[0] if parts else ""
    size = size_raw.replace("inch", "-inch") if size_raw.endswith("inch") else size_raw
    color_key = parts[1] if len(parts) > 1 else ""
    color = COLOR_MAP.get(color_key, color_key.title())
    chip = None
    cpu = None
    gpu = None
    # Format A: size-color-cpu-gpu (e.g. MacBook Air: 13inch-midnight-10-8)
    if len(parts) == 4:
        try:
            cpu = int(parts[2])
        except ValueError:
            cpu = None
        try:
            gpu = int(parts[3])
        except ValueError:
            gpu = None
    # Format B: size-color-tier-chip-cpu-gpu (e.g. MacBook Pro: 14inch-spaceblack-standard-m5pro-15-16)
    elif len(parts) >= 6:
        chip_key = parts[3]
        chip = CHIP_MAP.get(chip_key, chip_key.upper())
        try:
            cpu = int(parts[4])
        except ValueError:
            cpu = None
        try:
            gpu = int(parts[5])
        except ValueError:
            gpu = None
    cores = ""
    if cpu is not None and gpu is not None:
        cores = f"{cpu}-core CPU, {gpu}-core GPU"
    label = f"{size} {color}"
    if chip:
        label += f" · {chip}"
    if cores:
        label += f" ({cores})"
    return {"size": size, "color": color, "chip": chip, "cpu_cores": cpu, "gpu_cores": gpu, "label": label.strip()}


def parse_options(html: str) -> dict:
    m = re.search(r"window\.PRODUCT_SELECTION_BOOTSTRAP\s*=\s*(\{.*?\});", html, re.S)
    if not m:
        return {}
    txt = m.group(1)
    out = {}
    # memory options: all gb headers with small values (RAM)
    mem_opts = re.findall(r'"(\d+gb)":\{"header":"([^"]*)"', txt, re.I)
    mem_labels = []
    for key, header in mem_opts:
        val = int(key.replace("gb", ""))
        if val <= 128:
            mem_labels.append(re.sub(r"<[^>]+>", "", header).strip().replace("&nbsp;", " "))
    # dedupe
    seen = set()
    mem_dedup = []
    for h in mem_labels:
        if h not in seen:
            seen.add(h)
            mem_dedup.append(h)
    if mem_dedup:
        out["memory_options"] = mem_dedup
    # storage options: all tb headers
    stor_opts = re.findall(r'"(\d+tb)":\{"header":"([^"]*)"', txt, re.I)
    stor_labels = []
    seen = set()
    for key, header in stor_opts:
        h = re.sub(r"<[^>]+>", "", header).strip().replace("&nbsp;", " ")
        if h not in seen:
            seen.add(h)
            stor_labels.append(h)
    if stor_labels:
        out["storage_options"] = stor_labels
    return out


def parse_catalog_variants(html: str) -> list[dict]:
    """Join discrete products to their own option labels and prices."""
    from .configurator import plain_text
    match = re.search(r"\bproductSelectionData\s*:\s*", html)
    if not match:
        return []
    try:
        data, _ = json.JSONDecoder().raw_decode(html[match.end():])
        displays = data.get("displayValues")
        products = data.get("products")
        if not isinstance(displays, dict) or not isinstance(products, list):
            return []
        prices = displays.get("prices") or {}
        variants = []
        seen = set()
        for product in products:
            if not isinstance(product, dict) or not product.get("partNumber"):
                continue
            attributes = {}
            for dimension, values in displays.items():
                selected = product.get(dimension)
                if selected is None or not dimension.startswith("dimension") or not isinstance(values, dict):
                    continue
                option = values.get(selected) or {}
                if isinstance(option, dict):
                    attributes[dimension.removeprefix("dimension").lower()] = plain_text(option.get("value")) or str(selected)
            price = prices.get(product.get("fullPrice")) or {}
            identity = (product["partNumber"], price.get("amountBeforeTradeIn"),
                        price.get("priceCurrency"), tuple(sorted(attributes.items())))
            if identity in seen:
                continue
            seen.add(identity)
            variants.append({"part_number": product["partNumber"], "price": price.get("amountBeforeTradeIn"),
                             "currency": price.get("priceCurrency"), "attributes": attributes})
        return variants
    except (TypeError, ValueError, AttributeError):
        return []


def parse_variant_prices(html: str) -> list[dict]:
    m = re.search(r"window\.PRODUCT_SELECTION_BOOTSTRAP\s*=\s*(\{.*?\});", html, re.S)
    if not m:
        return []
    txt = m.group(1)
    out = []
    # iPhone-style: part numbers with amountBeforeTradeIn
    pairs = re.findall(r'"product":"([A-Z0-9/]+)"[^}]*"amountBeforeTradeIn":([\d.]+)', txt)
    from collections import defaultdict
    prices = defaultdict(set)
    for part, price in pairs:
        try:
            prices[part].add(float(price))
        except ValueError:
            continue
    if prices:
        # A price ordering does not prove a part number's capacity or color.
        for part, vals in sorted(prices.items(), key=lambda kv: min(kv[1])):
            out.append({"part_number": part, "name": None, "label": None, "size": None, "color": None,
                        "chip": None, "cpu_cores": None, "gpu_cores": None, "price": min(vals)})
    # Mac-style: configuration slugs with amount
    if not out:
        mac_pairs = re.findall(r'"([a-z0-9-]+)":\{"comparativeDisplayPrice"[^}]*"amount":([\d.]+)', txt)
        seen = set()
        for slug, price in mac_pairs:
            if slug in seen:
                continue
            seen.add(slug)
            try:
                dec = _decode_mac_slug(slug)
                out.append({"part_number": None, "name": slug, "label": dec["label"], "size": dec["size"],
                            "color": dec["color"], "chip": dec["chip"], "cpu_cores": dec["cpu_cores"],
                            "gpu_cores": dec["gpu_cores"], "price": float(price)})
            except ValueError:
                continue
    return out

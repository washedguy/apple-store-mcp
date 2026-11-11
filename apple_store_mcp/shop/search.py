"""Search Apple Store pages."""
from html.parser import HTMLParser
from urllib.parse import quote, urljoin

from .errors import RetailerError
from .http import fetch_text
from .parsing import parse_search


async def search_page(self, query, page=1, tab="explore"):
    prefix = self.prefix
    path_query = quote(query.strip(), safe="")
    url = f"{self.base}/{prefix}/search/{path_query}"
    params = []
    if page and page > 1:
        params.append(f"page={page}")
    if tab:
        params.append(f"tab={tab}")
    params.append("src=aos")
    if params:
        url = url + "?" + "&".join(params)
    try:
        html, final_url = await fetch_text(url)
    except RetailerError as exc:
        # Fallback to sitemap-based discovery when Apple blocks search.
        if exc.code in ("blocked", "rate_limited") and page == 1:
            try:
                sm = await sitemap(self, query.strip())
                return sitemap_search_result(self, query.strip(), sm, fallback=True)
            except RetailerError:
                raise
        raise
    try:
        result = parse_search(html, self.base, self.country, self.language, query.strip(), tab, page)
    except RetailerError:
        raise
    for p in result["products"]:
        if p.get("currency") is None:
            p["currency"] = self.currency
    result["retailer"] = "apple"
    result["country"] = self.country
    result["language"] = self.language
    result["redirected_url"] = None
    result["related_pages"] = None
    result["local_filters"] = None
    return result


def sitemap_search_result(client, query, sitemap_data, *, fallback=False):
    products = [{"id": None, "title": link["title"], "brand": None, "price": None,
                 "currency": None, "url": link["url"], "image": None, "type": "sitemap",
                 "delivery": {"status": "unknown", "retailer_status": None, "retailer_code": None,
                              "earliest": None, "preorder": False, "is_preorder": False},
                 "preorder": False, "is_preorder": False} for link in sitemap_data["links"]]
    return {"retailer": "apple", "country": client.country, "language": client.language,
            "query": query, "products": products, "count": len(products), "total_products": None,
            "page": 1, "next_page": None, "paging": {"current_page": 1, "page_count": None, "max_page": None},
            "source": "sitemap", "coverage": "sitemap_fallback" if fallback else "sitemap",
            "redirected_url": None, "related_pages": None, "local_filters": None,
            "note": ("Apple search was blocked. " if fallback else "") +
                    "Sitemap links are pages, not a complete product catalog; prices and individual variants are not included."}


async def search_sitemap(client, query):
    return sitemap_search_result(client, query, await sitemap(client, query))


async def search(self, query, page=1, tab="explore", brand=None, min_price=None, max_price=None):
    result = await self.search_page(query, page, tab)
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
    return result


class _SitemapParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_main = False
        self.href = None
        self.text = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "main":
            self.in_main = True
        elif tag == "a" and self.in_main:
            self.href = dict(attrs).get("href")
            self.text = []

    def handle_data(self, data):
        if self.href is not None:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            self.links.append((self.href, " ".join("".join(self.text).split())))
            self.href = None
        elif tag == "main":
            self.in_main = False


def parse_sitemap(html, base, query=None):
    parser = _SitemapParser()
    parser.feed(html)
    if not parser.links:
        raise RetailerError("Sitemap page did not contain sitemap links; the retailer may have changed the page.")
    links, seen = [], set()
    needle = " ".join((query or "").casefold().split())
    for href, title in parser.links:
        if not href or not title:
            continue
        full = urljoin(base, href)
        if full in seen:
            continue
        seen.add(full)
        haystack = " ".join((title + " " + href).casefold().split())
        if needle and needle not in haystack:
            continue
        links.append({"title": title, "url": full})
    return links


async def sitemap(self, query=None):
    """Fetch the country sitemap page and return its main links."""
    prefix = "" if self.country == "us" else f"/{self.site_prefix}"
    url = f"{self.base}{prefix}/sitemap/"
    html, final_url = await fetch_text(url)
    if "/sitemap" not in final_url:
        raise RetailerError("Apple redirected the sitemap request.", code="blocked")
    links = parse_sitemap(html, self.base, query)
    return {"retailer": "apple", "country": self.country, "language": self.language,
            "query": query, "links": links, "count": len(links)}

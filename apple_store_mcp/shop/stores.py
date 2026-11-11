"""Find Apple retail stores."""
from datetime import datetime, timezone

from .errors import RetailerError
from .http import fetch_text
from .parsing import parse_store_list, parse_store_page

_store_page_cache = {}


async def _enrich(self, entry):
    url = entry["url"]
    if url in _store_page_cache:
        parsed = _store_page_cache[url]
    else:
        try:
            page_html, _ = await fetch_text(url)
            parsed = parse_store_page(page_html)
        except RetailerError:
            parsed = None
        if parsed:
            _store_page_cache[url] = parsed
    store = {
        "id": entry.get("id"),
        "name": entry["name"],
        "url": url,
        "region": entry.get("region"),
        "address": {"street": None, "house_number": None, "postal_code": None, "city": None, "country": None},
        "position": {"latitude": None, "longitude": None},
        "phone": None,
    }
    if parsed:
        store["id"] = parsed.get("id") or store["id"]
        store["name"] = parsed.get("name") or store["name"]
        store["address"] = parsed.get("address") or store["address"]
        store["position"] = parsed.get("position") or store["position"]
        store["phone"] = parsed.get("phone")
    if not store.get("id"):
        store["id"] = url.rstrip("/").split("/")[-1]
    return store


def _matches(store, query_l):
    haystack = " ".join(str(v or "") for v in [
        store.get("name"), store.get("region"), store.get("url"),
        (store.get("address") or {}).get("city"),
        (store.get("address") or {}).get("postal_code"),
        (store.get("address") or {}).get("street"),
    ]).lower()
    return query_l in haystack


async def stores(self, query):
    query_l = query.strip().lower()
    candidates = []
    if self.site_prefix:
        candidates.append(f"{self.base}/{self.site_prefix}/retail/storelist/")
    if self.prefix and self.prefix != self.site_prefix:
        candidates.append(f"{self.base}/{self.prefix}/retail/storelist/")
    candidates.append(f"{self.base}/retail/storelist/")
    html = None
    for url in candidates:
        try:
            html, final_url = await fetch_text(url)
            break
        except RetailerError as exc:
            if exc.code == "not_found":
                continue
            raise
    if html is None:
        raise RetailerError("Store list page could not be retrieved.", code="not_found")
    entries = parse_store_list(html, self.base, self.country, self.language)

    # Direct filter against store-list names/regions.
    direct = [e for e in entries if query_l in f"{e.get('region','')} {e.get('name','')} {e.get('url','')}".lower()]
    selected_entries = direct if direct else entries

    # If no direct match, enrich all store pages to filter by city/postal code.
    enrich_all = not direct
    stores = []
    for e in selected_entries:
        store = await _enrich(self, e)
        if (not enrich_all) or _matches(store, query_l):
            stores.append(store)

    if enrich_all and not stores:
        # nothing matched; return empty rather than all
        stores = []

    # cap
    stores = stores[:25]
    return {
        "retailer": "apple",
        "country": self.country,
        "language": self.language,
        "query": query,
        "stores": stores,
        "count": len(stores),
    }

async def list_all(self):
    prefix = '' if self.country == 'us' else f'/{self.site_prefix}'
    html, final = await fetch_text(f'{self.base}{prefix}/retail/storelist/', retries=0)
    if '/retail/storelist' not in final:
        raise RetailerError('Apple redirected the store list request.', code='blocked')
    entries = parse_store_list(html, self.base, self.country, self.language)
    if not entries:
        raise RetailerError('Apple store list did not contain stores.', code='retailer_changed')
    return {'country': self.country, 'stores': entries, 'count': len(entries),
            'observed_at': datetime.now(timezone.utc).isoformat()}

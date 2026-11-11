"""Request configuration-dependent options from Apple's CTO endpoint."""
import json
import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlencode

from .errors import RetailerError
from .http import fetch_text

_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,120}$")


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "as-footnote") or self.hidden:
            self.hidden += 1

    def handle_endtag(self, tag):
        if self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value):
    if not isinstance(value, str):
        return None
    parser = _TextExtractor()
    parser.feed(value)
    return " ".join(unescape(" ".join(parser.parts)).replace("\u00ad", "").split())


def parse_configuration(text, currency):
    try:
        body = json.loads(text)["body"]
        options, prices = body["options"], body["prices"]
        if not isinstance(options, dict) or not isinstance(prices, dict):
            raise ValueError
        dimensions = []
        for name, data in options.items():
            choices = []
            for category, key in (("compatible", "compatibleOptions"), ("upgrade", "upgradeOptions")):
                for value, info in data.get(key, {}).items():
                    price = prices.get(info.get("priceDelta"), {})
                    choices.append({"value": value, "category": category,
                                    "price_delta": price.get("amount"),
                                    "display_price_delta": plain_text(price.get("displayPrice")),
                                    "selected": info.get("isSelected"),
                                    "default": info.get("isDefault"),
                                    "blocked": info.get("isBlocked")})
            dimensions.append({"name": name, "description": plain_text(data.get("dynamicFooter")), "choices": choices})
        kits = body.get("selectedKits") or {}
        selected = {name: value.get("dimensionValue") for name, value in kits.get("dimensions", {}).items()}
        price_data = kits.get("priceData") or {}
        return {"currency": currency, "dimensions": dimensions, "selected_dimensions": selected,
                "part_number": kits.get("btrOrFdPartNumber"),
                "container_part_number": kits.get("aosContainerPartNumber"),
                "product_configuration": kits.get("productConfiguration") or {},
                "selected_price": price_data.get("amount"),
                "selected_price_display": plain_text(price_data.get("comparativeDisplayPrice")),
                "reset": body.get("isReset")}
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise RetailerError("Apple returned an unexpected configurator response.", code="upstream_error") from exc


async def configuration(client, collection, selections, *, session=None, referer=None):
    if not _TOKEN.fullmatch(collection) or len(selections) > 30 or any(
        not _TOKEN.fullmatch(k) or not _TOKEN.fullmatch(v) for k, v in selections.items()
    ):
        raise RetailerError("Invalid collection or selection identifier.", code="invalid_input")
    params = {"collection": collection, "fae": "true", **{f"sv.{k}": v for k, v in selections.items()}}
    prefix = f"/{client.prefix}" if client.country != "us" else ""
    url = f"{client.base}{prefix}/shop/api/cto/update-config?{urlencode(params)}"
    text, final_url = await fetch_text(url, headers={"Accept": "application/json", "X-AOS-UI-Fetch-Call-1": "true", "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", **({"Referer": referer} if referer else {})}, session=session)
    if "/shop/api/cto/update-config" not in final_url:
        raise RetailerError("Apple redirected the configurator request.", code="blocked")
    result = parse_configuration(text, client.currency)
    return {"country": client.country, "language": client.language, "collection": collection,
            "requested_selections": selections, "observed_at": datetime.now(timezone.utc).isoformat(), **result}

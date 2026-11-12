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


async def upgrade_prices(client, html):
    """Fetch upgrade price deltas for RAM, storage, etc. from Apple's CTO endpoint."""
    # Extract collection ID
    coll_m = re.search(r"updateConfigUrl:\s*['\"]([^'\"]*collection=([A-Z0-9_]+)[^'\"]*)['\"]", html)
    if not coll_m:
        return {}
    collection = coll_m.group(2)
    # Extract default dimensions from first product in productSelectionData
    selections = {}
    m = re.search(r'"products"\s*:\s*(\[.*?\])\s*,\s*"mainDisplayValues"', html, re.S)
    if m:
        first = m.group(1).split('},{')[0] + '}'
        dm = re.search(r'"dimensions"\s*:\s*(\{.*?\})', first)
        if dm:
            for k, v in re.findall(r'"([a-z-]+-dimension[A-Za-z]+)":"([^"]*)"', dm.group(1)):
                selections[k] = v
    # Defaults for memory/storage (base config)
    if "memory-dimensionMemory" not in selections:
        selections["memory-dimensionMemory"] = "16gb"
    if "storage-dimensionCapacity" not in selections:
        selections["storage-dimensionCapacity"] = "1tb"
    if "power_adapter-wattage" not in selections:
        selections["power_adapter-wattage"] = "0w"
    if "keyboard-localizationCode" not in selections:
        selections["keyboard-localizationCode"] = "deu"
    if "software_logic-preInstalledSoftware" not in selections:
        selections["software_logic-preInstalledSoftware"] = "none"
    if "software_final-preInstalledSoftware" not in selections:
        selections["software_final-preInstalledSoftware"] = "none"
    # Build base selections from the first product
    base_selections = dict(selections)
    if "memory-dimensionMemory" not in base_selections:
        base_selections["memory-dimensionMemory"] = "16gb"
    if "storage-dimensionCapacity" not in base_selections:
        base_selections["storage-dimensionCapacity"] = "1tb"
    if "power_adapter-wattage" not in base_selections:
        base_selections["power_adapter-wattage"] = "0w"
    if "keyboard-localizationCode" not in base_selections:
        base_selections["keyboard-localizationCode"] = "deu"
    if "software_logic-preInstalledSoftware" not in base_selections:
        base_selections["software_logic-preInstalledSoftware"] = "none"
    if "software_final-preInstalledSoftware" not in base_selections:
        base_selections["software_final-preInstalledSoftware"] = "none"

    # Chips to try
    chips = ["m6", "m5pro", "m5max", "m5", "m4"]
    chip_cpu = {
        "m6": "m6-12-12", "m5pro": "m5pro-15-16", "m5max": "m5max-18-32",
        "m5": "m5-10-10", "m4": "m4-10-10",
    }
    # Memory defaults per chip
    chip_mem_default = {"m6": "16gb", "m5pro": "24gb", "m5max": "36gb", "m5": "16gb", "m4": "16gb"}
    # Storage defaults
    chip_stor_default = {"m6": "1tb", "m5pro": "1tb", "m5max": "1tb", "m5": "1tb", "m4": "1tb"}

    result = {}
    for chip in chips:
        sel = dict(base_selections)
        sel["processor-dimensionChip"] = chip
        sel["processor-dimensionChip-cpuCoreCount-gpuCoreCount"] = chip_cpu.get(chip, chip_cpu["m6"])
        sel["memory-dimensionMemory"] = chip_mem_default.get(chip, "16gb")
        sel["storage-dimensionCapacity"] = chip_stor_default.get(chip, "1tb")

        # Call with sections to get memory + storage + display
        try:
            r = await configuration(client, collection, sel)
        except RetailerError:
            continue
        dims = r.get("dimensions", [])
        if not dims:
            continue
        chip_data = {}
        for dim in dims:
            name = dim["name"]
            choices = []
            for c in dim.get("choices", []):
                choices.append({
                    "value": c["value"],
                    "price_delta": c.get("price_delta"),
                    "display_price_delta": c.get("display_price_delta"),
                    "is_default": c.get("default"),
                    "is_blocked": c.get("blocked"),
                })
            if choices:
                chip_data[name] = choices
        if chip_data:
            result[chip] = chip_data

    return result

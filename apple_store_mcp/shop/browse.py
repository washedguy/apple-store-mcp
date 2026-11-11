"""Discover buy links and present Apple's live configurator with readable labels."""
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .configurator import configuration, plain_text
from .delivery import configuration_delivery, delivery
from .errors import RetailerError
from .fulfillment import fulfillment, variant_pickup
from .http import fetch_text
from .products import APPLE_HOSTS
from .parsing import parse_catalog_variants


def _valid_url(url, host):
    try:
        p = urlsplit(url)
        return p.scheme == 'https' and p.hostname == host and p.username is None and p.port is None
    except ValueError:
        return False


class BuyLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current = None
        self.in_main = False

    def handle_starttag(self, tag, attrs):
        if tag == 'main':
            self.in_main = True
        if tag == 'a' and self.in_main:
            attrs = dict(attrs)
            href = attrs.get('href', '')
            if '/shop/goto/buy_' in href or '/shop/buy-' in href:
                self.current = [href, attrs.get('aria-label') or attrs.get('data-analytics-title'), []]

    def handle_data(self, data):
        if self.current is not None:
            self.current[2].append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            href, label, text = self.current
            self.links.append((href, label or ' '.join(''.join(text).split())))
            self.current = None
        elif tag == 'main':
            self.in_main = False


def _metadata(html):
    match = re.search(r'\bproductSelectionData\s*:\s*', html)
    if not match:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(html[match.end():])
        if not isinstance(data, dict) or not isinstance(data.get('products'), list):
            return None
        return data
    except ValueError:
        return None


def _key(name):
    # Generic dimension names keep the interface independent of particular products.
    tail = name.split('-')[-1]
    aliases = {'dimensionScreensize': 'screen_size', 'dimensionCapacity': 'storage',
               'dimensionMemory': 'memory', 'dimensionColor': 'color',
               'dimensionFinish': 'display', 'localizationCode': 'keyboard',
               'gpuCoreCount': 'cpu_gpu', 'wattage': 'power_adapter'}
    if tail == 'preInstalledSoftware':
        return name.split('-')[0]
    if tail in aliases:
        return aliases[tail]
    tail = re.sub(r'^(dimension|localization)', '', tail, flags=re.I)
    return re.sub(r'(?<!^)(?=[A-Z])', '_', tail).lower()


def _normalize(s):
    return re.sub(r'[^\w]', '', s.casefold())


def _labels(data):
    result = {}
    for field in ('mainDisplayValues', 'configDisplayValues'):
        for name, values in data.get(field, {}).items():
            if not isinstance(values, dict) or '-' not in name:
                continue
            result[name] = {k: plain_text(re.split(r'<(?:div|p|br)\b', v.get('header') or '', maxsplit=1, flags=re.I)[0]) or k
                            for k, v in values.items() if isinstance(v, dict)}
    return result


def _resolve_requested(requested, labels):
    resolved = {}
    for short, value in requested.items():
        dimensions = [name for name in labels if _normalize(short) in (_normalize(_key(name)), _normalize(name))]
        if len(dimensions) != 1:
            raise RetailerError(f"Unknown or ambiguous option '{short}'. Choose a name shown in options.", code='invalid_input')
        name = dimensions[0]
        matches = [key for key, label in labels[name].items() if _normalize(value) in (_normalize(key), _normalize(label))]
        if len(matches) != 1:
            raise RetailerError(f"Unknown or ambiguous value '{value}' for '{short}'. Choose a value shown in options.", code='invalid_input')
        resolved[name] = matches[0]
    return resolved


async def browse(client, url, requested=None, location=None, postal_code=None):
    requested = requested or {}
    if not _valid_url(url, client.host) or urlsplit(url).hostname not in APPLE_HOSTS:
        raise RetailerError('Use an HTTPS Apple URL for the selected storefront.', code='invalid_input')
    html, final = await fetch_text(url, retries=0)
    if not _valid_url(final, client.host):
        raise RetailerError('Apple redirected to an unexpected host.', code='blocked')
    data = _metadata(html)
    if data is None:
        parser = BuyLinks()
        parser.feed(html)
        choices, seen = [], set()
        for href, label in parser.links:
            target = urljoin(final, href)
            if target not in seen and _valid_url(target, client.host):
                seen.add(target)
                choices.append({'name': label, 'url': target})
        if not choices:
            raise RetailerError('No supported buy choices or configurator were found on this page.', code='retailer_changed')
        if requested or location or postal_code:
            raise RetailerError('Choose a buy option from this page before setting options or a location.', code='invalid_input')
        return {'kind': 'choices', 'url': final, 'choices': choices,
                'observed_at': datetime.now(timezone.utc).isoformat()}
    variants = parse_catalog_variants(html)
    if variants:
        for name, value in requested.items():
            variants = [v for v in variants if any(_normalize(name) == _normalize(k) and
                        _normalize(value) == _normalize(val) for k, val in v['attributes'].items())]
        out = {'kind': 'variants', 'url': final, 'currency': client.currency, 'variants': variants,
               'observed_at': datetime.now(timezone.utc).isoformat()}
        parts = list(dict.fromkeys(v['part_number'] for v in variants))
        if (location or postal_code) and not parts:
            raise RetailerError('No variants match the selected options.', code='invalid_input')
        if location:
            try:
                pickup = await variant_pickup(client, final, parts, location)
                out.update({'stores': pickup['stores'], 'location': location,
                            'availability_observed_at': pickup['observed_at']})
            except RetailerError as exc:
                out.setdefault('issues', []).append({'stage': 'pickup', 'code': exc.code, 'message': str(exc)})
        if postal_code:
            try:
                out['delivery'] = await delivery(client, final, parts, postal_code)
            except RetailerError as exc:
                out.setdefault('issues', []).append({'stage': 'delivery', 'code': exc.code, 'message': str(exc)})
        return out
    collections = list(dict.fromkeys(re.findall(r'collection=([A-Z0-9_]+_COLLECTION)', html)))
    if len(collections) != 1:
        raise RetailerError('Could not identify a unique configurator for this product.', code='retailer_changed')
    labels = _labels(data)
    resolved = _resolve_requested(requested, labels)
    prices = data.get('mainDisplayValues', {}).get('prices', {})
    candidates = [p for p in data['products'] if isinstance(p, dict) and isinstance(p.get('dimensions'), dict)
                  and all(p['dimensions'].get(k) == v for k, v in resolved.items() if k in p['dimensions'])]
    if not candidates:
        raise RetailerError('No matching base configuration was found; try fewer selections.', code='invalid_input')
    def sort_price(item):
        amount = prices.get(item.get('priceKey'), {}).get('amount')
        return amount if isinstance(amount, (int, float)) else float('inf')
    base = min(candidates, key=sort_price)['dimensions']
    selections = {**base, **resolved}
    result = await configuration(client, collections[0], selections)
    if result['reset'] or any(result['selected_dimensions'].get(k) != v for k, v in resolved.items()):
        raise RetailerError('Apple could not apply those choices together. Try another combination.', code='invalid_input')
    dimensions = []
    for dim in result['dimensions']:
        name = dim['name']
        selected = result['selected_dimensions'].get(name)
        choices = []
        for choice in dim['choices']:
            value = choice['value']
            choices.append({'name': labels.get(name, {}).get(value, value), 'value': value,
                            'compatible': choice['category'] == 'compatible' and not choice['blocked'],
                            'requires_changes': choice['category'] == 'upgrade',
                            'price_change': choice['price_delta']})
        dimensions.append({'name': _key(name), 'selected': labels.get(name, {}).get(selected, selected), 'choices': choices})
    out = {'kind': 'configuration', 'url': final, 'currency': result['currency'],
           'price': result['selected_price'], 'price_display': result['selected_price_display'],
           'selection': {dim['name']: dim['selected'] for dim in dimensions if dim['selected'] is not None},
           'options': dimensions, 'observed_at': result['observed_at']}
    if location:
        try:
            pickup = await fulfillment(client, final, collections[0], result['selected_dimensions'], location)
            out['stores'] = pickup['stores']
            out['location'] = location
            out['availability_observed_at'] = pickup['observed_at']
        except RetailerError as exc:
            out.setdefault('issues', []).append({'stage': 'pickup', 'code': exc.code, 'message': str(exc)})
    if postal_code:
        try:
            out['delivery'] = await configuration_delivery(client, final, collections[0], result['selected_dimensions'], postal_code)
        except RetailerError as exc:
            out.setdefault('issues', []).append({'stage': 'delivery', 'code': exc.code, 'message': str(exc)})
    return out

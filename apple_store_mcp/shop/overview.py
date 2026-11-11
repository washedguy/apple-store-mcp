"""Read-only product overview: model prices first, availability when identifiable."""
import re
from datetime import datetime, timezone

from .browse import BuyLinks, _key, _labels, _metadata, _resolve_requested, _valid_url, browse
from .errors import RetailerError
from .http import fetch_text
from .parsing import _ld_json_products, parse_catalog_variants
from .search import sitemap
from urllib.parse import urljoin
from .configurator import plain_text


def _words(text):
    return set(re.findall(r'[^\W_]+', text.casefold()))


def _matching_choices(query, choices):
    tokens = _words(query)
    scored = [(len(tokens & _words(choice['name'])), choice) for choice in choices]
    if not scored:
        return []
    highest = max(score for score, _ in scored)
    best = [choice for score, choice in scored if score == highest]
    return [choice for choice in best if tokens.issubset(_words(choice['name']))]


def _best_choice(query, choices):
    matches = _matching_choices(query, choices)
    return matches[0] if len(matches) == 1 else None


async def _locate(client, product):
    if product.startswith('https://'):
        return product
    words = product.strip().split()
    if not words or len(product) > 200:
        raise RetailerError('Provide a product name or Apple product URL.', code='invalid_input')
    # The sitemap typically names product families rather than every model.
    for end in range(len(words), 0, -1):
        result = await sitemap(client, ' '.join(words[:end]))
        links = [{'name': x['title'], 'url': x['url']} for x in result['links']]
        if links:
            if len(links) == 1:
                return links[0]['url']
            best = _best_choice(product, links)
            if best and end == len(words):
                return best['url']
            raise RetailerError('Several product pages match. Use search_products to choose one.', code='invalid_input')
    raise RetailerError('No matching product page was found in the sitemap.', code='not_found')


async def overview(client, product, options=None, location=None, postal_code=None):
    requested = options or {}
    url = await _locate(client, product)
    if not _valid_url(url, client.host):
        raise RetailerError('Use a product URL from the selected Apple storefront.', code='invalid_input')
    html, final = await fetch_text(url, retries=0)
    if not _valid_url(final, client.host):
        raise RetailerError('Apple redirected to an unexpected host.', code='blocked')
    data = _metadata(html)
    if data is None:
        parser = BuyLinks()
        parser.feed(html)
        links, seen = [], set()
        for href, name in parser.links:
            target = urljoin(final, href)
            if target not in seen and _valid_url(target, client.host):
                links.append({'name': name, 'url': target})
                seen.add(target)
        if not links:
            raise RetailerError('No supported product information was found on this page.', code='retailer_changed')
        matches = _matching_choices(product, links) if not product.startswith('https://') else []
        choice = matches[0] if len(matches) == 1 else None
        if len(links) == 1:
            choice = links[0]
        resolved = None
        if choice is None and len(matches) > 1:
            # Distinct links can lead to the same product. Verify redirects rather
            # than guessing that similarly named links are equivalent.
            destinations = []
            for match in matches:
                try:
                    page, target = await fetch_text(match['url'], retries=0)
                except RetailerError:
                    destinations = []
                    break
                if not _valid_url(target, client.host):
                    destinations = []
                    break
                destinations.append((page, target))
            if destinations and len({target for _, target in destinations}) == 1:
                resolved = destinations[0]
                choice = matches[0]
        if choice is None:
            return {'kind': 'choices', 'product': product, 'country': client.country,
                    'url': final, 'choices': matches or links, 'observed_at': datetime.now(timezone.utc).isoformat(),
                    'note': 'More than one product matches. Choose a page to see its prices.'}
        html, final = resolved or await fetch_text(choice['url'], retries=0)
        if not _valid_url(final, client.host):
            raise RetailerError('Apple redirected to an unexpected host.', code='blocked')
        data = _metadata(html)
    if data is None:
        raise RetailerError('Apple did not provide a supported product overview.', code='retailer_changed')
    product_data = _ld_json_products(html)
    title = product_data[0].get('name') if product_data else None
    discrete = parse_catalog_variants(html)
    if discrete:
        result = await browse(client, final, requested, location, postal_code)
        items = [{'attributes': v.get('attributes') or {},
                  'attribute_descriptions': v.get('attribute_descriptions') or {}, 'price': v.get('price'),
                  'currency': v.get('currency') or client.currency,
                  'part_number': v.get('part_number')} for v in result['variants']]
        return {'kind': 'products', 'product': title or product, 'country': client.country, 'url': final,
                'observed_at': result['observed_at'], 'currency': client.currency, 'variants': items,
                'delivery': result.get('delivery'), 'stores': result.get('stores'),
                'availability_observed_at': result.get('availability_observed_at'), 'issues': result.get('issues', []),
                'note': 'Prices are for the listed variants; availability is checked only when a location or postal code is provided.'}
    labels = _labels(data)
    resolved = _resolve_requested(requested, labels)
    prices = (data.get('mainDisplayValues') or {}).get('prices') or {}
    items, seen = [], set()
    for item in data.get('products', []):
        dims = item.get('dimensions') if isinstance(item, dict) else None
        if not isinstance(dims, dict):
            continue
        if any(dims.get(k) != v for k, v in resolved.items() if k in dims):
            continue
        p = prices.get(item.get('priceKey')) or {}
        amount = p.get('amount')
        attrs = {_key(k): labels.get(k, {}).get(v, v) for k, v in dims.items()}
        identity = (tuple(sorted(attrs.items())), amount)
        if identity in seen:
            continue
        seen.add(identity)
        items.append({'attributes': attrs, 'price': amount, 'price_display': plain_text(p.get('comparativeDisplayPrice')),
                      'currency': client.currency})
    if not items:
        raise RetailerError('No matching configurations were found.', code='invalid_input')
    items.sort(key=lambda x: (x['price'] is None, x['price'] if x['price'] is not None else 0))
    # Config-only dimensions cannot be priced by a page's base price map.
    base_keys = {k for item in data['products'] if isinstance(item, dict) for k in (item.get('dimensions') or {})}
    extra = [k for k in resolved if k not in base_keys]
    if extra:
        exact = await browse(client, final, requested, location, postal_code)
        return {'kind': 'configuration', 'product': title or product, 'country': client.country, 'url': final,
                'currency': exact['currency'], 'observed_at': exact['observed_at'],
                'variants': [{'attributes': exact['selection'], 'price': exact['price'],
                              'price_display': exact['price_display'], 'currency': exact['currency']}],
                'options': exact['options'], 'stores': exact.get('stores'), 'delivery': exact.get('delivery'),
                'availability_observed_at': exact.get('availability_observed_at'), 'issues': exact.get('issues', []),
                'note': 'This is one matching configuration, including Apple-selected defaults. Its price and availability do not cover other configurations.'}
    available_options = [{'name': _key(k), 'values': list(dict.fromkeys(v.values()))} for k, v in labels.items()]
    out = {'kind': 'products', 'product': title or product, 'country': client.country, 'url': final,
           'observed_at': datetime.now(timezone.utc).isoformat(), 'currency': client.currency,
           'variants': items, 'available_options': available_options,
           'note': 'These are Apple’s base-configuration prices. Memory and storage upgrades can change the price and may depend on the chip.'}
    if location or postal_code:
        if len(items) == 1:
            exact = await browse(client, final, requested, location, postal_code)
            out.update({'stores': exact.get('stores'), 'delivery': exact.get('delivery'),
                        'availability_observed_at': exact.get('availability_observed_at'), 'issues': exact.get('issues', []),
                        'availability_configuration': exact['selection']})
            out['note'] += ' Availability applies only to the returned configuration, including Apple-selected defaults.'
        else:
            out['note'] += ' Narrow the options to one base configuration to check its availability; no availability was assumed.'
    return out

"""Retrieve fulfillment using a newly established Apple Store session."""
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

from .configurator import configuration
from .errors import RetailerError
from .http import _session, fetch_text


def parse_fulfillment(text):
    try:
        pickup = json.loads(text)['body']
        if not isinstance(pickup, dict) or not isinstance(pickup.get('stores'), list):
            raise ValueError
        stores = []
        for store in pickup.get('stores') or []:
            availability = []
            for part in (store.get('partsAvailability') or {}).values():
                availability.append({
                    'part_number': part.get('partNumber'),
                    'eligible': part.get('storePickEligible'),
                    'status': {'available': 'available', 'unavailable': 'unavailable',
                               'ships-to-store': 'ships_to_store'}.get(part.get('pickupDisplay'), 'unknown'),
                    'display': part.get('pickupDisplay'),
                    'quote': part.get('pickupSearchQuote'),
                })
            stores.append({'id': store.get('storeNumber'), 'name': store.get('storeName'),
                           'city': store.get('city'), 'availability': availability})
        return stores
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise RetailerError('Apple returned an unexpected fulfillment response.', code='upstream_error') from exc


async def fulfillment(client, buy_url, collection, selections, location):
    if not location.strip() or len(location) > 150:
        raise RetailerError("A city or postal code is required.", code="invalid_input")
    try:
        url = urlsplit(buy_url)
        expected_prefix = '' if client.country == 'us' else f'/{client.prefix}'
        valid = (url.scheme == 'https' and url.hostname == client.host and url.port is None
                 and url.username is None and url.path.startswith(f'{expected_prefix}/shop/buy-')
                 and not url.query and not url.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise RetailerError('Use a buy-page HTTPS URL for the selected storefront.', code='invalid_input')
    async with _session(timeout=20) as session:
        html, final_url = await fetch_text(buy_url, retries=0, session=session)
        final = urlsplit(final_url)
        if final.scheme != 'https' or final.hostname != client.host or not final.path.startswith(f'{expected_prefix}/shop/buy-'):
            raise RetailerError('Apple redirected the buy page unexpectedly.', code='blocked')
        if 'PRODUCT_SELECTION_BOOTSTRAP' not in html:
            raise RetailerError('Apple did not return a recognizable buy page.', code='upstream_error')
        config = await configuration(client, collection, selections, session=session, referer=final_url)
        if config['reset']:
            raise RetailerError('Apple reset the requested configuration.', code='invalid_input')
        if any(config['selected_dimensions'].get(key) != value for key, value in selections.items()):
            raise RetailerError('Apple selected different dimensions; check the configuration first.', code='invalid_input')
        part, options = config['container_part_number'], config['product_configuration']
        if not part or not options:
            raise RetailerError('Apple did not return the parts needed for fulfillment.', code='upstream_error')
        params = {'pl': 'true', 'location': location.strip(), 'parts.0': part,
                  'option.0': ','.join(options.values()), 'mts.0': 'regular'}
        endpoint = f'{client.base}{expected_prefix}/shop/retail/pickup-message?{urlencode(params)}'
        text, final = await fetch_text(endpoint, retries=0, session=session,
                                       headers={'Accept': '*/*', 'Referer': final_url,
                                                'Sec-Fetch-Dest': 'empty', 'Sec-Fetch-Mode': 'cors',
                                                'X-AOS-UI-Fetch-Call-1': 'true'})
        if urlsplit(final).path != f'{expected_prefix}/shop/retail/pickup-message':
            raise RetailerError('Apple redirected the fulfillment request.', code='blocked')
        stores = parse_fulfillment(text)
    return {'country': client.country, 'language': client.language, 'observed_at': datetime.now(timezone.utc).isoformat(),
            'selected_dimensions': config['selected_dimensions'], 'configuration': config, 'stores': stores,
            'location_scope': location.strip(),
            'note': 'Quotes are Apple pickup estimates, not an exact stock count or reservation.'}


async def variant_pickup(client, buy_url, parts, location):
    try:
        url = urlsplit(buy_url)
        prefix = '' if client.country == 'us' else f'/{client.prefix}'
        valid = (url.scheme == 'https' and url.hostname == client.host and url.port is None
                 and url.username is None and url.path.startswith(f'{prefix}/shop/buy-')
                 and not url.query and not url.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise RetailerError('Use an Apple buy-page URL for the selected storefront.', code='invalid_input')
    if not parts or len(parts) > 20 or any(not re.fullmatch(r'[A-Za-z0-9/-]{3,40}', p) for p in parts):
        raise RetailerError('Provide one to 20 valid part numbers.', code='invalid_input')
    if not location.strip() or len(location) > 150:
        raise RetailerError('Provide a city or postal code.', code='invalid_input')
    async with _session(timeout=20) as session:
        _, final = await fetch_text(buy_url, retries=0, session=session)
        parsed = urlsplit(final)
        if parsed.scheme != 'https' or parsed.hostname != client.host or not parsed.path.startswith(f'{prefix}/shop/buy-'):
            raise RetailerError('Apple redirected the buy page unexpectedly.', code='blocked')
        params = {'pl': 'true', 'location': location.strip(), 'mts.0': 'regular',
                  **{f'parts.{i}': part for i, part in enumerate(parts)}}
        endpoint = f'{client.base}{prefix}/shop/retail/pickup-message?{urlencode(params)}'
        text, target = await fetch_text(endpoint, retries=0, session=session,
                                        headers={'Accept': '*/*', 'Referer': final, 'Sec-Fetch-Dest': 'empty', 'Sec-Fetch-Mode': 'cors'})
        if urlsplit(target).path != f'{prefix}/shop/retail/pickup-message':
            raise RetailerError('Apple redirected the pickup request.', code='blocked')
        stores = parse_fulfillment(text)
    return {'country': client.country, 'language': client.language, 'location': location.strip(),
            'observed_at': datetime.now(timezone.utc).isoformat(), 'stores': stores}

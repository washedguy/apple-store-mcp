"""Fetch Apple's read-only delivery estimates for discrete part numbers."""
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

from .configurator import plain_text
from .errors import RetailerError
from .http import _session, fetch_text


def parse_delivery(text, parts):
    try:
        messages = json.loads(text)['body']['content']['deliveryMessage']
        if not isinstance(messages, dict):
            raise ValueError
        results = []
        for part in parts:
            data = (messages.get(part) or {}).get('regular') or {}
            choices = []
            messages_for_options = data.get('deliveryOptionMessages') or []
            for option in data.get('deliveryOptions') or []:
                matching_dates = [m.get('encodedUpperDateString') for m in messages_for_options
                                  if option.get('date') and option['date'] in (m.get('displayName') or '')]
                upper_date = matching_dates[0] if len(matching_dates) == 1 else None
                if isinstance(upper_date, str) and re.fullmatch(r'\d{8}', upper_date):
                    upper_date = f'{upper_date[:4]}-{upper_date[4:6]}-{upper_date[6:]}'
                else:
                    upper_date = None
                choices.append({'method': plain_text(option.get('displayName')),
                                'date': plain_text(option.get('date')),
                                'latest_date': upper_date,
                                'shipping_cost': plain_text(option.get('shippingCost'))})
            results.append({'part_number': part, 'product': plain_text(data.get('subHeader')),
                            'options': choices, 'available': None,
                            'note': None if choices else 'Apple did not return a delivery estimate for this part.'})
        return results
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RetailerError('Apple returned an unexpected delivery response.', code='upstream_error') from exc


async def delivery(client, buy_url, parts, postal_code):
    try:
        url = urlsplit(buy_url)
        prefix = '' if client.country == 'us' else f'/{client.prefix}'
        valid = (url.scheme == 'https' and url.hostname == client.host and url.port is None
                 and url.username is None and url.path.startswith(f'{prefix}/shop/buy-')
                 and not url.query and not url.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise RetailerError('Use a buy-page URL for the selected storefront.', code='invalid_input')
    if not parts or len(parts) > 20 or any(not re.fullmatch(r'[A-Za-z0-9/-]{3,40}', p) for p in parts):
        raise RetailerError('Provide one to 20 valid part numbers.', code='invalid_input')
    if not postal_code.strip() or len(postal_code) > 32:
        raise RetailerError('Provide a postal code.', code='invalid_input')
    async with _session(timeout=20) as session:
        _, final = await fetch_text(buy_url, retries=0, session=session)
        if urlsplit(final).hostname != client.host or not urlsplit(final).path.startswith(f'{prefix}/shop/buy-'):
            raise RetailerError('Apple redirected the buy page unexpectedly.', code='blocked')
        params = {'fae': 'true', 'postalCode': postal_code.strip(), 'mts.0': 'regular',
                  **{f'parts.{i}': part for i, part in enumerate(parts)}}
        endpoint = f'{client.base}{prefix}/shop/delivery-message?{urlencode(params)}'
        text, result_url = await fetch_text(endpoint, retries=0, session=session,
                                             headers={'Accept': '*/*', 'Referer': final,
                                                      'Sec-Fetch-Dest': 'empty', 'Sec-Fetch-Mode': 'cors',
                                                      'X-AOS-UI-Fetch-Call-1': 'true'})
        if urlsplit(result_url).path != f'{prefix}/shop/delivery-message':
            raise RetailerError('Apple redirected the delivery request.', code='blocked')
        results = parse_delivery(text, parts)
    return {'country': client.country, 'language': client.language, 'postal_code': postal_code.strip(),
            'observed_at': datetime.now(timezone.utc).isoformat(), 'products': results}

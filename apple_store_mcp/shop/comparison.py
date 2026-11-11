"""Compare read-only delivery and pickup checks with explicit coverage."""
from datetime import datetime, timezone

from .delivery import delivery
from .errors import RetailerError
from .fulfillment import variant_pickup
from .stores import _enrich, list_all


def _error(exc):
    return {'code': exc.code, 'message': str(exc)}


async def compare(client, buy_url, parts, locations, postal_codes, all_stores=False):
    if not parts or len(parts) > 20 or not (locations or postal_codes or all_stores):
        raise RetailerError('Provide 1–20 parts and at least one location, postal code or all_stores.', code='invalid_input')
    if len(locations) > 30 or len(postal_codes) > 20:
        raise RetailerError('At most 30 pickup locations and 20 delivery postcodes are supported.', code='invalid_input')
    if any(not value.strip() for value in [*locations, *postal_codes]):
        raise RetailerError('Locations and postal codes must not be blank.', code='invalid_input')
    directory = []
    errors = []
    locations = list(dict.fromkeys(location.strip() for location in locations))
    if all_stores:
        directory = (await list_all(client))['stores']
        if len(directory) > 30:
            raise RetailerError('This country has more than 30 stores; provide specific locations instead.', code='unsupported')
        for entry in directory:
            store = await _enrich(client, entry)
            address = store.get('address') or {}
            location = address.get('postal_code') or address.get('city')
            if location and location not in locations:
                locations.append(location)
            elif not location:
                errors.append({'stage': 'store_location', 'input': entry['name'],
                               'code': 'unknown', 'message': 'Could not determine a location for this store.'})
    store_map = {}
    directory_ids = {entry['id'] for entry in directory if entry.get('id')}
    for location in locations:
        try:
            result = await variant_pickup(client, buy_url, parts, location)
            for store in result['stores']:
                if not store.get('id'):
                    errors.append({'stage': 'pickup', 'input': location, 'code': 'unknown',
                                   'message': 'Apple returned a store without an identifier.'})
                    continue
                key = store['id']
                if all_stores and key not in directory_ids:
                    continue
                if key not in store_map:
                    store_map[key] = {**store, 'observed_at': result['observed_at'], 'queried_near': location}
        except RetailerError as exc:
            errors.append({'stage': 'pickup', 'input': location, **_error(exc)})
    delivery_results = []
    for postal_code in dict.fromkeys(code.strip() for code in postal_codes):
        try:
            delivery_results.append(await delivery(client, buy_url, parts, postal_code))
        except RetailerError as exc:
            errors.append({'stage': 'delivery', 'input': postal_code, **_error(exc)})
    stores = list(store_map.values())
    # Missing results are returned explicitly, not inferred to be out of stock.
    missing_parts = [{'store_id': s['id'], 'part_number': part} for s in stores for part in parts
                     if part not in {q.get('part_number') for q in s['availability']}]
    unknown_parts = [{'store_id': s['id'], 'part_number': q['part_number']} for s in stores
                     for q in s['availability'] if q.get('part_number') in parts and q.get('status') == 'unknown']
    unknown_delivery = [{'postal_code': r['postal_code'], 'part_number': p['part_number']}
                        for r in delivery_results for p in r['products'] if not p['options']]
    checked_ids = set(store_map)
    missing_stores = [{'id': e.get('id'), 'name': e['name']} for e in directory if e.get('id') not in checked_ids]
    return {'country': client.country, 'language': client.language, 'part_numbers': parts,
            'observed_at': datetime.now(timezone.utc).isoformat(), 'pickup': stores,
            'delivery': delivery_results, 'errors': errors, 'directory_checked': all_stores,
            'directory_store_count': len(directory) if all_stores else None,
            'missing_stores': missing_stores, 'missing_parts': missing_parts,
            'unknown_parts': unknown_parts, 'unknown_delivery': unknown_delivery,
            'complete': not errors and not missing_stores and not missing_parts and not unknown_parts and not unknown_delivery,
            'note': 'Quotes are estimates. Missing or failed checks have unknown availability.'}

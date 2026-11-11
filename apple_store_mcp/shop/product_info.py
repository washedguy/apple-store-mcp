"""Compact product prices and option requirements for read-only comparisons."""
from .browse import browse
from .errors import RetailerError
from .overview import overview


def _price(amount, currency, kind, *, display=None):
    if amount is None:
        return None
    return {'amount': amount, 'currency': currency, 'kind': kind, 'display': display}


def _group_variants(variants, currency):
    groups = {}
    for variant in variants:
        for key, name in variant.get('attributes', {}).items():
            values = groups.setdefault(key, {})
            existing = values.get(name)
            amount = variant.get('price')
            if existing is None:
                values[name] = {'name': name, 'description': variant.get('attribute_descriptions', {}).get(key),
                                'price': _price(amount, currency, 'starting_at'), 'requirements': []}
            elif amount is not None and (existing['price'] is None or amount < existing['price']['amount']):
                existing['price'] = _price(amount, currency, 'starting_at')
    return groups


async def product_info(client, product, options=None, location=None, postal_code=None):
    data = await overview(client, product, options, location, postal_code)
    if data['kind'] == 'choices':
        return {**data, 'options': {}, 'variants': [], 'issues': []}
    variants = data.get('variants') or []
    currency = data.get('currency') or client.currency
    groups = _group_variants(variants, currency)
    if variants and all(v.get('part_number') for v in variants):
        # Report observed pairings in the returned catalog; do not claim an
        # exhaustive or universal compatibility rule.
        for key, values in groups.items():
            for name, entry in values.items():
                matching = [v for v in variants if v.get('attributes', {}).get(key) == name]
                for other in groups:
                    if other == key or not all(other in v.get('attributes', {}) for v in variants):
                        continue
                    all_values = list(dict.fromkeys(v['attributes'][other] for v in variants))
                    allowed = list(dict.fromkeys(v['attributes'][other] for v in matching))
                    if allowed and len(allowed) < len(all_values):
                        entry['requirements'].append({'status': 'observed_with', 'when': 'listed_variants',
                            'dimension': other, 'values': allowed,
                            'description': 'Observed together in the returned variants; this may not describe every possible combination.'})
    result = {'kind': data['kind'], 'product': data['product'], 'url': data['url'],
              'country': client.country, 'currency': currency, 'observed_at': data['observed_at'],
              'variants': variants, 'stores': data.get('stores'), 'delivery': data.get('delivery'),
              'availability_observed_at': data.get('availability_observed_at'),
              'availability_configuration': data.get('availability_configuration'),
              'issues': data.get('issues', []), 'note': data.get('note')}
    for dim in data.get('available_options') or []:
        values = groups.setdefault(dim['name'], {})
        for name in dim['values']:
            values.setdefault(name, {'name': name, 'description': None, 'price': None, 'requirements': []})
    dynamic = None
    if data['kind'] == 'configuration':
        dynamic = {'options': data.get('options') or [],
                   'selection': variants[0]['attributes'] if variants else {}}
    elif variants and not any(v.get('part_number') for v in variants):
        # These deltas and compatibility come from one explicitly identified example,
        # not from testing every combination.
        dynamic = await browse(client, data['url'], options or {})
    if dynamic and dynamic.get('kind') != 'variants':
        examples = [dynamic]
        # Compare one example per observed chip/core pairing; size and other
        # dimensions may still affect compatibility.
        pairs = list(dict.fromkeys((v.get('attributes', {}).get('chip'), v.get('attributes', {}).get('cpu_gpu'))
                                   for v in variants if v.get('attributes', {}).get('chip')))
        if not options and len(pairs) <= 8:
            for chip, cores in pairs:
                if (chip, cores) == (dynamic.get('selection', {}).get('chip'), dynamic.get('selection', {}).get('cpu_gpu')):
                    continue
                try:
                    constraints = {'chip': chip}
                    if cores:
                        constraints['cpu_gpu'] = cores
                    examples.append(await browse(client, data['url'], constraints))
                except RetailerError as exc:
                    result['issues'].append({'stage': 'requirements', 'code': exc.code, 'message': str(exc)})
        result['example_configuration'] = dynamic.get('selection') or {}
        result['example_configurations'] = {}
        for index, example in enumerate(examples, start=1):
            context = example.get('selection') or {}
            context_id = f'example_{index}'
            result['example_configurations'][context_id] = context
            for dimension in example.get('options') or []:
                values = groups.setdefault(dimension['name'], {})
                for choice in dimension['choices']:
                    name = choice['name']
                    entry = values.setdefault(name, {'name': name, 'description': None, 'price': None, 'requirements': []})
                    status = ('unavailable_or_unknown' if choice.get('blocked') is True else
                              'compatible' if choice['compatible'] else
                              'requires_changes' if choice['requires_changes'] else 'unavailable_or_unknown')
                    change = choice.get('price_change')
                    entry['requirements'].append({'status': status, 'when': context_id,
                        'price_change': _price(change, currency, 'change_from_example'),
                        'description': 'Observed for this example configuration; other combinations were not evaluated.'})
                    if index == 1 and entry['price'] is None and change is not None:
                        entry['price'] = _price(change, currency, 'change_from_example')
    result['options'] = {key: list(values.values()) for key, values in groups.items()}
    if dynamic:
        result['note'] = (result.get('note') or '') + ' Option price changes and requirements apply only to the named examples; they are not a complete requirements matrix. The price of kind change_from_example uses example_1.'
    return result

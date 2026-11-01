from collections import Counter, defaultdict
from pipeline.normalize.common import supplier_key


def summarize(records):
    groups = defaultdict(lambda: {'cents': 0, 'count': 0})
    for record in records:
        key = (record['memberId'], record['year'], record['month'], record['party'], record['category'], record['inMandate'])
        groups[key]['cents'] += record['cents']
        groups[key]['count'] += 1
    return [{'memberId': key[0], 'year': key[1], 'month': key[2], 'party': key[3],
             'category': key[4], 'inMandate': key[5], **value} for key, value in sorted(groups.items())]


def summarize_suppliers(records, year):
    groups = defaultdict(lambda: {'cents': 0, 'count': 0, 'names': Counter(), 'ids': Counter()})
    unidentified = defaultdict(lambda: {'cents': 0, 'count': 0})
    for record in records:
        if record['year'] != year:
            raise ValueError('Ano divergente no agregado de fornecedores')
        key = supplier_key(record.get('supplierId'), record['id'])
        if key.startswith('unidentified:'):
            unidentified[record['memberId']]['cents'] += record['cents']
            unidentified[record['memberId']]['count'] += 1
            continue
        group_key = (key, record['memberId'], record['year'])
        group = groups[group_key]
        group['cents'] += record['cents']
        group['count'] += 1
        name = (record.get('supplier') or '').strip()
        if name:
            group['names'][name] += 1
        raw_id = (record.get('supplierId') or '').strip()
        if raw_id:
            group['ids'][raw_id] += 1

    rows = []
    for (key, member_id, row_year), value in sorted(groups.items()):
        supplier_name = value['names'].most_common(1)[0][0] if value['names'] else 'Fornecedor não informado'
        supplier_id = value['ids'].most_common(1)[0][0] if value['ids'] else key
        rows.append({
            'supplierKey': key,
            'supplier': supplier_name,
            'supplierId': supplier_id,
            'memberId': member_id,
            'year': row_year,
            'cents': value['cents'],
            'count': value['count']
        })

    unidentified_rows = [
        {'memberId': member_id, 'year': year, 'cents': value['cents'], 'count': value['count']}
        for member_id, value in sorted(unidentified.items())
    ]
    return {'year': year, 'unidentified': unidentified_rows, 'rows': rows}

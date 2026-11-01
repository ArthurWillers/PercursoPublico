import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from pipeline.normalize.common import cents, auxiliary_cents, iso_date, official_url, party_at, in_mandate, UNKNOWN_PARTY

API = 'https://dadosabertos.camara.leg.br/api/v2'


def registry(client):
    members = {}
    url = API + '/deputados?itens=100'
    visited = set()
    while url:
        if url in visited:
            raise ValueError('Ciclo na paginação de deputados')
        visited.add(url)
        response = client.json(url)
        for row in response['dados']:
            key = 'camara:' + str(row['id'])
            if key in members:
                raise ValueError('Deputado duplicado na paginação')
            members[key] = row
        url = next((link['href'] for link in response['links'] if link['rel'] == 'next'), None)
    if len(members) < 400:
        raise ValueError('Cadastro atual da Câmara inesperadamente incompleto')
    return members


def annual_rows(client, year):
    url = f'https://www.camara.leg.br/cotas/Ano-{year}.csv.zip'
    with zipfile.ZipFile(io.BytesIO(client.get(url, cache_days=client.historical_cache_days(year)))) as archive:
        files = [name for name in archive.namelist() if name.lower().endswith('.csv')]
        if len(files) != 1:
            raise ValueError('Arquivo CEAP inesperado')
        with archive.open(files[0]) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding='utf-8-sig'), delimiter=';')
            required = {'ideCadastro', 'nuDeputadoId', 'numAno', 'numMes', 'vlrLiquido', 'ideDocumento', 'txtDescricao'}
            if not required <= set(reader.fieldnames or []):
                raise ValueError('Contrato CEAP mudou')
            rows = list(reader)
    if not rows:
        raise ValueError(f'CEAP vazia: {year}')
    return rows, url


def affiliations_from_history(history, legislatures, today):
    events = sorted([row for row in history if row.get('siglaPartido') and row.get('dataHora')
                     and row['idLegislatura'] in legislatures
                     and legislatures[row['idLegislatura']]['dataInicio'] <= row['dataHora'][:10]
                     <= min(today, legislatures[row['idLegislatura']]['dataFim'])],
                    key=lambda row: (row['dataHora'], row['idLegislatura']))
    by_day = {}
    for row in events:
        by_day.setdefault(row['dataHora'][:10], []).append(row)
    affiliations = []
    for day, rows in sorted(by_day.items()):
        parties = [row['siglaPartido'] for row in rows]
        end = legislatures[rows[-1]['idLegislatura']]['dataFim']
        conflicting = len(set(parties)) > 1
        if affiliations and affiliations[-1]['party'] == parties[-1] and affiliations[-1]['end'] >= day and not conflicting:
            continue
        if affiliations:
            affiliations[-1]['end'] = min(affiliations[-1]['end'], (date.fromisoformat(day) - timedelta(days=1)).isoformat())
            if affiliations[-1]['end'] < affiliations[-1]['start']:
                affiliations.pop()
        if conflicting:
            affiliations.append({'start': day, 'end': day, 'party': UNKNOWN_PARTY})
            day = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        affiliations.append({'start': day, 'end': end, 'party': parties[-1]})
    return affiliations


def latest_legislature(history, today):
    exercises = [row for row in history if row.get('situacao') == 'Exercício'
                 and row.get('dataHora') and row['dataHora'][:10] <= today]
    return max(exercises, key=lambda row: (row['dataHora'], row['idLegislatura']))['idLegislatura'] if exercises else None


def mandate_from_history(history, legislatures, today):
    identifier = latest_legislature(history, today)
    if identifier is None:
        return None
    exercises = [row['dataHora'][:10] for row in history
                 if row.get('idLegislatura') == identifier and row.get('situacao') == 'Exercício'
                 and row.get('dataHora') and row['dataHora'][:10] <= today]
    exits = [row['dataHora'][:10] for row in history if row.get('idLegislatura') == identifier
             and row.get('dataHora') and max(exercises) <= row['dataHora'][:10] <= today
             and 'Afastamento definitivo' in (row.get('descricaoStatus') or '')]
    return {'start': min(exercises), 'end': min(exits) if exits else legislatures[identifier]['dataFim'], 'partial': True}


def expense_portal_url(row, year, month):
    portal_member_id = (row.get('nuDeputadoId') or '').strip()
    if not portal_member_id.isdigit():
        raise ValueError('Identificador CEAP do parlamentar inválido')
    period = f'{month}/{year}'
    parameters = {
        'cnpjFornecedor': '',
        'dataFim': period,
        'dataInicio': period,
        'despesa': '',
        'filtroNivel1': '1',
        'filtroNivel2': '2',
        'filtroNivel3': '3',
        'nomeFornecedor': '',
        'nomeHospede': '',
        'nomePassageiro': '',
        'nuDeputadoId': portal_member_id,
        'numDocumento': (row.get('txtNumero') or '').strip(),
        'sguf': '',
    }
    return 'https://www.camara.leg.br/cota-parlamentar/sumarizado?' + urlencode(parameters)


def profiles(client, ids, current):
    today = date.today().isoformat()
    def fetch_history(key):
        source_id = key.split(':')[1]
        if isinstance(current, dict) and isinstance(current.get(key), dict) and 'nome' in current[key]:
            details = {'ultimoStatus': current[key]}
            return key, details, client.json(API + '/deputados/' + source_id + '/historico', cache_days=0)['dados']
        cache_days = 0 if key in current else 365
        history = client.json(API + '/deputados/' + source_id + '/historico', cache_days=cache_days)['dados']
        try:
            details = client.json(API + '/deputados/' + source_id, cache_days=cache_days)['dados']
        except (HTTPError, URLError, TimeoutError) as exc:
            if isinstance(exc, HTTPError):
                exc.close()
            if not history:
                raise
            latest = max(history, key=lambda row: (row.get('dataHora') or '', row.get('idLegislatura') or 0))
            details = {
                'ultimoStatus': {
                    'nome': (latest.get('nome') or latest.get('nomeEleitoral') or '').strip(),
                    'siglaPartido': (latest.get('siglaPartido') or '').rstrip('*').strip() or None,
                    'siglaUf': latest.get('siglaUf') or '',
                    'urlFoto': latest.get('urlFoto')
                }
            }
        return key, details, history
    with ThreadPoolExecutor(max_workers=4) as executor:
        histories = list(executor.map(fetch_history, sorted(ids)))
    legislature_ids = {row['idLegislatura'] for _key, _details, history in histories for row in history if row.get('idLegislatura')}
    legislatures = {identifier: client.json(f'{API}/legislaturas/{identifier}', cache_days=365)['dados']
                    for identifier in sorted(legislature_ids)}
    def collect(entry):
        key, details, history = entry
        source_id = key.split(':')[1]
        status = details['ultimoStatus']
        affiliations = affiliations_from_history(history, legislatures, today)
        valid_history = [row for row in history if row.get('dataHora') and row.get('idLegislatura') in legislatures
                         and legislatures[row['idLegislatura']]['dataInicio'] <= row['dataHora'][:10]
                         <= legislatures[row['idLegislatura']]['dataFim']]
        mandate = mandate_from_history(valid_history, legislatures, today)
        return key, {'id': key, 'name': status['nome'].strip(), 'chamber': 'deputados',
                     'party': status.get('siglaPartido') or 'Não informado', 'state': status['siglaUf'],
                     'photoUrl': official_url(status.get('urlFoto')), 'sourceUrl': API + '/deputados/' + source_id,
                     'current': key in current, 'mandate': mandate, 'affiliations': affiliations}
    return dict(map(collect, histories))


def normalize(rows, year, members, source_url):
    occurrences = Counter()
    records = []
    unattributed = {'records': 0, 'cents': 0}
    for index, row in enumerate(rows, 2):
        amount = cents(row['vlrLiquido'])
        actual_year, month = int(row['numAno']), int(row['numMes'])
        if actual_year != year or month not in range(1, 13):
            raise ValueError('Competência CEAP inválida')
        if not row['ideCadastro']:
            unattributed['records'] += 1
            unattributed['cents'] += amount
            continue
        member_id = 'camara:' + row['ideCadastro']
        if member_id not in members:
            raise ValueError(f'Deputado sem cadastro: {member_id}')
        # ideDocumento identifica o documento, não a linha. Todas as ocorrências ficam.
        fingerprint = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        occurrences[fingerprint] += 1
        expense_id = f'camara:{year}:{fingerprint}:{occurrences[fingerprint]}'
        issued_at = iso_date(row['datEmissao'])
        member = members[member_id]
        records.append({'id': expense_id, 'memberId': member_id, 'year': year, 'month': month,
                        'cents': amount, 'category': row['txtDescricao'], 'categoryOriginal': row['txtDescricao'], 'categoryCode': row['numSubCota'],
                        'party': party_at(member['affiliations'], issued_at, year, month),
                        'partyReported': row['sgPartido'] or None,
                        'inMandate': in_mandate(member['mandate'], year, month),
                        'supplier': row['txtFornecedor'], 'supplierId': row['txtCNPJCPF'] or None,
                        'issuedAt': issued_at, 'documentId': row['ideDocumento'] or None,
                        'documentNumber': row['txtNumero'], 'documentType': row['indTipoDocumento'],
                        'documentUrl': official_url(row['urlDocumento']), 'portalUrl': expense_portal_url(row, actual_year, month),
                        'sourceUrl': source_url,
                        'sourceRecord': str(index), 'grossCents': auxiliary_cents(row['vlrDocumento']),
                        'grossAmountOriginal': row['vlrDocumento'] or None,
                        'disallowedCents': auxiliary_cents(row['vlrGlosa']),
                        'disallowedAmountOriginal': row['vlrGlosa'] or None,
                        'restitutionCents': auxiliary_cents(row['vlrRestituicao']),
                        'restitutionAmountOriginal': row['vlrRestituicao'] or None,
                        'restitutionAt': row['datPagamentoRestituicao'] or None,
                        'installment': row['numParcela'], 'batch': row['numLote'],
                        'reimbursement': row['numRessarcimento']})
    return records, unattributed

"""Coleta e normalização das prestações de contas eleitorais do TSE (Eleições Gerais e Municipais)."""
import csv
import io
import zipfile
from collections import Counter, defaultdict
from urllib.error import HTTPError, URLError
from pipeline.normalize.common import cents, supplier_key

CDN = 'https://cdn.tse.jus.br/estatistica/sead/odsele'
GENERAL_ELECTION_YEARS = (2010, 2014, 2018, 2022, 2026)
MUNICIPAL_ELECTION_YEARS = (2008, 2012, 2016, 2020, 2024)
ELECTION_YEARS = (2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024, 2026)
MAX_VEREADOR_CANDIDATES = 5000

GENERAL_OFFICES = {
    '5': 'senador',
    '6': 'deputado_federal',
    'SENADOR': 'senador',
    'DEPUTADO FEDERAL': 'deputado_federal'
}
MUNICIPAL_OFFICES = {
    '11': 'prefeito',
    '13': 'vereador',
    'PREFEITO': 'prefeito',
    'VEREADOR': 'vereador'
}
ALL_OFFICES = {**GENERAL_OFFICES, **MUNICIPAL_OFFICES}


def election_scope(year):
    return 'municipal' if year in MUNICIPAL_ELECTION_YEARS else 'geral'


def candidates_url(year):
    return f'{CDN}/consulta_cand/consulta_cand_{year}.zip'


def accounts_url(year):
    return f'{CDN}/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{year}.zip'


def accounts_candidate_urls(year):
    return (
        f'{CDN}/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{year}.zip',
        f'{CDN}/prestacao_contas/prestacao_final_{year}.zip',
        f'{CDN}/prestacao_contas/prestacao_contas_{year}.zip'
    )


def _clean_field(value):
    text = (value or '').strip()
    if text in ('#NULO', '#NULO#', '#NE', '#NE#', '-1', '-3', '-4'):
        return ''
    return text


def _first_field(row, *names):
    for name in names:
        val = row.get(name)
        if val is not None:
            cleaned = _clean_field(val)
            if cleaned:
                return cleaned
    return ''


def _normalize_result(raw_result):
    text = _clean_field(raw_result).upper()
    if text == 'ELEITO POR QP':
        return 'Eleito por QP', True
    if text in ('ELEITO POR MÉDIA', 'ELEITO POR MEDIA'):
        return 'Eleito por média', True
    if text == 'ELEITO':
        return 'Eleito', True
    if text in ('2º TURNO', 'SEGUNDO TURNO'):
        return '2º turno', False
    if text == 'SUPLENTE':
        return 'Suplente', False
    if text in ('NÃO ELEITO', 'NAO ELEITO'):
        return 'Não eleito', False
    return (_clean_field(raw_result).capitalize() or 'Sem totalização'), False


def _classify_revenue(origin, source):
    origin_upper = _clean_field(origin).upper()
    source_upper = _clean_field(source).upper()
    if 'FUNDO ESPECIAL' in source_upper or 'FUNDO ESPECIAL' in origin_upper or 'FEFC' in source_upper or 'FEFC' in origin_upper:
        return 'fefcCents'
    if 'FUNDO PARTID' in source_upper or 'FUNDO PARTID' in origin_upper:
        return 'partyFundCents'
    if 'PESSOAS FÍSICAS' in origin_upper or 'PESSOAS FISICAS' in origin_upper or 'FINANCIAMENTO COLETIVO' in origin_upper or 'RECURSOS DE PESSOAS FÍSICAS' in origin_upper or 'RECURSOS DE PESSOAS FISICAS' in origin_upper:
        return 'individualCents'
    if 'RECURSOS PRÓPRIOS' in origin_upper or 'RECURSOS PROPRIOS' in origin_upper:
        return 'ownResourcesCents'
    return 'otherRevenueCents'


def _resolve_office(row, year=None):
    allowed = MUNICIPAL_OFFICES if year in MUNICIPAL_ELECTION_YEARS else (GENERAL_OFFICES if year in GENERAL_ELECTION_YEARS else ALL_OFFICES)
    code = _first_field(row, 'CD_CARGO', 'COD_CARGO')
    if code in allowed:
        return allowed[code]
    description = _first_field(row, 'DS_CARGO', 'DESCRICAO_CARGO').upper()
    return allowed.get(description)


def _extract_municipality(row, office):
    if office not in ('prefeito', 'vereador'):
        return None, None
    mun_name = _first_field(row, 'NM_UE', 'DS_UE', 'DESCRICAO_UE', 'NM_MUNICIPIO') or 'Município não informado'
    mun_code = _first_field(row, 'SG_UE', 'SIGLA_UE', 'CD_MUNICIPIO') or None
    return mun_name, mun_code


def _new_candidate_entry(sq, year, office, row, default_result):
    name = _first_field(row, 'NM_CANDIDATO', 'NOME_CANDIDATO') or f'Candidatura {sq}'
    ballot_name = _first_field(row, 'NM_URNA_CANDIDATO', 'NOME_URNA_CANDIDATO') or name
    ballot_number = _first_field(row, 'NR_CANDIDATO', 'NUMERO_CANDIDATO', 'NR_CAND')
    party = _first_field(row, 'SG_PARTIDO', 'SIGLA_PARTIDO') or 'Sem partido'
    state = _first_field(row, 'SG_UF', 'UF') or 'BR'
    municipality, municipality_code = _extract_municipality(row, office)
    result_label, elected = (default_result, False) if default_result else _normalize_result(
        _first_field(row, 'DS_SIT_TOT_TURNO', 'DESC_SIT_TOT_TURNO', 'DESC_SIT_CAND_TOT')
    )
    return {
        'id': f'tse:{year}:{sq}',
        'sqCandidato': sq,
        'year': year,
        'office': office,
        'name': name,
        'ballotName': ballot_name,
        'ballotNumber': ballot_number,
        'party': party,
        'state': state,
        'municipality': municipality,
        'municipalityCode': municipality_code,
        'result': result_label,
        'elected': elected,
        'totalRevenueCents': 0,
        'fefcCents': 0,
        'partyFundCents': 0,
        'individualCents': 0,
        'ownResourcesCents': 0,
        'otherRevenueCents': 0,
        'revenueCount': 0,
        'totalExpenseCents': 0,
        'expenseCount': 0,
        '_categories': defaultdict(lambda: {'cents': 0, 'count': 0})
    }


def normalize_election(candidate_rows, revenue_rows, expense_rows, year, source_urls, fetched_at=None, max_vereador_candidates=MAX_VEREADOR_CANDIDATES):
    scope = election_scope(year)
    candidates = {}
    for row in candidate_rows:
        office = _resolve_office(row, year)
        if not office:
            continue
        sq = _first_field(row, 'SQ_CANDIDATO', 'SEQUENCIAL_CANDIDATO')
        if not sq.isdigit():
            raise ValueError(f'SQ_CANDIDATO inválido no TSE ({year}): {sq!r}')
        entry = _new_candidate_entry(sq, year, office, row, default_result=None)
        existing = candidates.get(sq)
        if existing and existing['elected'] and not entry['elected']:
            continue
        candidates[sq] = entry

    for row in revenue_rows:
        sq = _first_field(row, 'SQ_CANDIDATO', 'SEQUENCIAL_CANDIDATO')
        office = _resolve_office(row, year)
        if sq not in candidates:
            if not office or not sq.isdigit():
                continue
            candidates[sq] = _new_candidate_entry(sq, year, office, row, default_result='Prestação de contas sem totalização')
        raw_revenue = _first_field(row, 'VR_RECEITA', 'VALOR_RECEITA') or '0'
        amount = cents(raw_revenue, brazilian=True)
        origin = _first_field(row, 'DS_ORIGEM_RECEITA', 'DESC_ORIGEM_RECEITA', 'TIPO_RECEITA')
        source = _first_field(row, 'DS_FONTE_RECEITA', 'DS_FONTE_RECURSO', 'FONTE_RECURSO')
        bucket = _classify_revenue(origin, source)
        candidate = candidates[sq]
        candidate[bucket] += amount
        candidate['totalRevenueCents'] += amount
        candidate['revenueCount'] += 1

    supplier_groups = defaultdict(lambda: {
        'cents': 0,
        'count': 0,
        'names': Counter(),
        'ids': Counter(),
        'offices': set(),
        'states': set(),
        'parties': set(),
        'by_candidate': defaultdict(lambda: {'cents': 0, 'count': 0})
    })
    unidentified_suppliers = {'cents': 0, 'count': 0}

    for index, row in enumerate(expense_rows, 1):
        sq = _first_field(row, 'SQ_CANDIDATO', 'SEQUENCIAL_CANDIDATO')
        office = _resolve_office(row, year)
        if sq not in candidates:
            if not office or not sq.isdigit():
                continue
            candidates[sq] = _new_candidate_entry(sq, year, office, row, default_result='Prestação de contas sem totalização')
        raw_amount = _first_field(row, 'VR_DESPESA_CONTRATADA', 'VR_DESPESA', 'VALOR_DESPESA', 'VR_PAGAMENTO') or '0'
        amount = cents(raw_amount, brazilian=True)
        candidate = candidates[sq]
        candidate['totalExpenseCents'] += amount
        candidate['expenseCount'] += 1
        category_name = (
            _first_field(row, 'DS_ORIGEM_DESPESA', 'DS_TIPO_DESPESA', 'DESC_TIPO_DESPESA', 'TIPO_DESPESA')
            or 'Despesa não classificada pela fonte'
        )
        candidate['_categories'][category_name]['cents'] += amount
        candidate['_categories'][category_name]['count'] += 1

        raw_supplier_id = _first_field(row, 'NR_CPF_CNPJ_FORNECEDOR', 'CPF_CNPJ_FORNECEDOR', 'CD_CPF_CNPJ_FORNECEDOR')
        key = supplier_key(raw_supplier_id, f'tse:{year}:exp:{index}')
        if key.startswith('unidentified:'):
            unidentified_suppliers['cents'] += amount
            unidentified_suppliers['count'] += 1
            continue

        group = supplier_groups[key]
        group['cents'] += amount
        group['count'] += 1
        supplier_name = _first_field(row, 'NM_FORNECEDOR_RFB', 'NM_FORNECEDOR', 'NOME_FORNECEDOR')
        if supplier_name:
            group['names'][supplier_name] += 1
        if raw_supplier_id:
            group['ids'][raw_supplier_id] += 1
        group['offices'].add(candidate['office'])
        group['states'].add(candidate['state'])
        group['parties'].add(candidate['party'])
        group['by_candidate'][sq]['cents'] += amount
        group['by_candidate'][sq]['count'] += 1

    all_candidates = []
    party_groups = defaultdict(lambda: {
        'candidacyCount': 0,
        'electedCount': 0,
        'totalRevenueCents': 0,
        'fefcCents': 0,
        'partyFundCents': 0,
        'individualCents': 0,
        'ownResourcesCents': 0,
        'otherRevenueCents': 0,
        'totalExpenseCents': 0,
        'expenseCount': 0
    })

    for sq, candidate in sorted(candidates.items(), key=lambda item: (-item[1]['totalRevenueCents'], -item[1]['totalExpenseCents'], item[0])):
        categories_map = candidate.pop('_categories')
        top_categories = [
            {'category': cat_name, 'cents': stats['cents'], 'count': stats['count']}
            for cat_name, stats in sorted(categories_map.items(), key=lambda item: (-item[1]['cents'], item[0]))[:8]
        ]
        candidate['topCategories'] = top_categories
        all_candidates.append(candidate)

        p_group = party_groups[(candidate['party'], candidate['office'])]
        p_group['candidacyCount'] += 1
        if candidate['elected']:
            p_group['electedCount'] += 1
        for field in (
            'totalRevenueCents', 'fefcCents', 'partyFundCents',
            'individualCents', 'ownResourcesCents', 'otherRevenueCents',
            'totalExpenseCents', 'expenseCount'
        ):
            p_group[field] += candidate[field]

    vereador_candidates = [c for c in all_candidates if c['office'] == 'vereador']
    if max_vereador_candidates is not None and len(vereador_candidates) > max_vereador_candidates:
        prioritized_vereadores = sorted(
            vereador_candidates,
            key=lambda c: (not c['elected'], -c['totalRevenueCents'], -c['totalExpenseCents'], c['sqCandidato'])
        )
        kept_vereador_ids = {c['id'] for c in prioritized_vereadores[:max_vereador_candidates]}
        normalized_candidates = []
        agg_groups = defaultdict(lambda: {
            'candidacyCount': 0,
            'electedCount': 0,
            'totalRevenueCents': 0,
            'fefcCents': 0,
            'partyFundCents': 0,
            'individualCents': 0,
            'ownResourcesCents': 0,
            'otherRevenueCents': 0,
            'totalExpenseCents': 0,
            'expenseCount': 0
        })
        for cand in all_candidates:
            if cand['office'] == 'vereador' and cand['id'] not in kept_vereador_ids:
                a_group = agg_groups[(cand['party'], cand['office'], cand['state'])]
                a_group['candidacyCount'] += 1
                if cand['elected']:
                    a_group['electedCount'] += 1
                for field in (
                    'totalRevenueCents', 'fefcCents', 'partyFundCents',
                    'individualCents', 'ownResourcesCents', 'otherRevenueCents',
                    'totalExpenseCents', 'expenseCount'
                ):
                    a_group[field] += cand[field]
            else:
                normalized_candidates.append(cand)
        aggregated_candidates = [
            {
                'party': party,
                'office': office,
                'state': state,
                'year': year,
                **stats
            }
            for (party, office, state), stats in sorted(agg_groups.items())
        ]
    else:
        normalized_candidates = all_candidates
        aggregated_candidates = []

    normalized_parties = [
        {
            'party': party,
            'office': office,
            'year': year,
            **stats
        }
        for (party, office), stats in sorted(party_groups.items(), key=lambda item: (-item[1]['totalRevenueCents'], item[0]))
    ]

    normalized_suppliers = []
    for key, group in sorted(supplier_groups.items(), key=lambda item: (-item[1]['cents'], item[0])):
        supplier_name = group['names'].most_common(1)[0][0] if group['names'] else 'Fornecedor não informado'
        supplier_id = group['ids'].most_common(1)[0][0] if group['ids'] else key
        top_cands = []
        for sq, stats in sorted(group['by_candidate'].items(), key=lambda item: (-item[1]['cents'], item[0]))[:10]:
            cand = candidates[sq]
            top_cands.append({
                'id': cand['id'],
                'ballotName': cand['ballotName'],
                'party': cand['party'],
                'state': cand['state'],
                'municipality': cand['municipality'],
                'office': cand['office'],
                'cents': stats['cents'],
                'count': stats['count']
            })
        normalized_suppliers.append({
            'supplierKey': key,
            'supplier': supplier_name,
            'supplierId': supplier_id,
            'year': year,
            'cents': group['cents'],
            'count': group['count'],
            'candidacyCount': len(group['by_candidate']),
            'offices': sorted(group['offices']),
            'states': sorted(group['states']),
            'parties': sorted(group['parties']),
            'topCandidates': top_cands
        })

    return {
        'year': year,
        'scope': scope,
        'status': 'collected',
        'reason': None,
        'fetchedAt': fetched_at,
        'sourceUrls': source_urls,
        'candidates': normalized_candidates,
        'aggregatedCandidates': aggregated_candidates,
        'parties': normalized_parties,
        'suppliers': {
            'unidentified': unidentified_suppliers,
            'rows': normalized_suppliers
        }
    }


def unavailable_election(year, reason):
    return {
        'year': year,
        'scope': election_scope(year),
        'status': 'unavailable',
        'reason': reason,
        'fetchedAt': None,
        'sourceUrls': {
            'candidates': candidates_url(year),
            'accounts': accounts_url(year)
        },
        'candidates': [],
        'aggregatedCandidates': [],
        'parties': [],
        'suppliers': {
            'unidentified': {'cents': 0, 'count': 0},
            'rows': []
        }
    }


def _read_csv_from_zip(raw_bytes, prefixes, year=None):
    if isinstance(prefixes, str):
        prefixes = (prefixes,)
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        archive_names = [
            name for name in archive.namelist()
            if name.lower().endswith(('.csv', '.txt')) and 'leiame' not in name.lower() and 'notas' not in name.lower()
        ]
        matched_names = []
        for prefix in prefixes:
            matched_names = [name for name in archive_names if prefix in name.lower()]
            if matched_names:
                break
        if not matched_names:
            raise ValueError(f'CSV {prefixes!r} não encontrado no pacote TSE')
        brasil_files = [name for name in matched_names if 'brasil' in name.lower()]
        selected = brasil_files or matched_names
        for filename in sorted(selected):
            with archive.open(filename) as raw:
                reader = csv.DictReader(io.TextIOWrapper(raw, encoding='latin-1', errors='replace'), delimiter=';')
                for row in reader:
                    if _resolve_office(row, year):
                        yield row


def collect_election_year(client, year):
    cand_url = candidates_url(year)
    acc_url = accounts_url(year)
    cache_days = client.historical_cache_days(year)
    try:
        cand_bytes = client.get(cand_url, cache_days=cache_days)
    except (HTTPError, URLError, TimeoutError, FileNotFoundError) as exc:
        return unavailable_election(
            year,
            f'Pacote de candidaturas eleitorais {year} ainda não disponível ou inacessível na origem ({exc.__class__.__name__}).'
        )

    acc_bytes = None
    last_exc = None
    for candidate_acc_url in accounts_candidate_urls(year):
        try:
            acc_bytes = client.get(candidate_acc_url, cache_days=cache_days)
            acc_url = candidate_acc_url
            break
        except (HTTPError, URLError, TimeoutError, FileNotFoundError) as exc:
            last_exc = exc
            continue

    if acc_bytes is None:
        return unavailable_election(
            year,
            f'Pacote de prestação de contas eleitorais {year} ainda não disponível ou inacessível na origem ({last_exc.__class__.__name__}).'
        )

    try:
        candidate_rows = list(_read_csv_from_zip(cand_bytes, ('consulta_cand',), year=year))
        revenue_rows = list(_read_csv_from_zip(acc_bytes, ('receitas_candidatos',), year=year))
        expense_rows = list(_read_csv_from_zip(acc_bytes, ('despesas_contratadas_candidatos', 'despesas_candidatos'), year=year))
    except (ValueError, KeyError, zipfile.BadZipFile) as exc:
        return unavailable_election(
            year,
            f'Formato do pacote eleitoral {year} incompatível ou incompleto na origem ({exc}).'
        )

    fetched_at = client.sources.get(acc_url, {}).get('fetchedAt')
    return normalize_election(
        candidate_rows,
        revenue_rows,
        expense_rows,
        year,
        {'candidates': cand_url, 'accounts': acc_url},
        fetched_at=fetched_at
    )

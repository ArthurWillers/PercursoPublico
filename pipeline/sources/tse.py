"""Coleta e normalização das prestações de contas eleitorais do TSE (Eleições Gerais e Municipais)."""
import csv
import gzip
import hashlib
from http.client import IncompleteRead, RemoteDisconnected
import io
import json
import os
import struct
import time
import zipfile
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from pipeline.normalize.common import cents, supplier_key

CDN = 'https://cdn.tse.jus.br/estatistica/sead/odsele'
GENERAL_ELECTION_YEARS = (2010, 2014, 2018, 2022, 2026)
MUNICIPAL_ELECTION_YEARS = (2008, 2012, 2016, 2020, 2024)
ELECTION_YEARS = (2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024, 2026)
MAX_VEREADOR_CANDIDATES = 2500
MAX_ELECTION_SUPPLIERS = 1000
CACHE_SCHEMA_TAG = 'v4-situacao'
MUNICIPAL_CACHE_SCHEMA_TAG = 'v3-situacao'

GENERAL_OFFICES = {
    '1': 'presidente',
    '3': 'governador',
    'PRESIDENTE': 'presidente',
    'GOVERNADOR': 'governador',
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
    if year in (2008, 2010, 2016):
        return f'{CDN}/prestacao_contas/prestacao_contas_{year}.zip'
    if year in (2012, 2014):
        return f'{CDN}/prestacao_contas/prestacao_final_{year}.zip'
    return f'{CDN}/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{year}.zip'


def accounts_candidate_urls(year):
    primary = accounts_url(year)
    fallbacks = (
        f'{CDN}/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{year}.zip',
        f'{CDN}/prestacao_contas/prestacao_final_{year}.zip',
        f'{CDN}/prestacao_contas/prestacao_contas_{year}.zip'
    )
    return (primary,) + tuple(u for u in fallbacks if u != primary)


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
    if (
        'PESSOAS FÍSICAS' in origin_upper
        or 'PESSOAS FISICAS' in origin_upper
        or 'FINANCIAMENTO COLETIVO' in origin_upper
        or 'PESSOA FÍSICA' in origin_upper
        or 'PESSOA FISICA' in origin_upper
    ):
        return 'individualCents'
    if 'RECURSOS PRÓPRIOS' in origin_upper or 'RECURSOS PROPRIOS' in origin_upper:
        return 'ownResourcesCents'
    return 'otherRevenueCents'


def _allowed_offices(year):
    if year in MUNICIPAL_ELECTION_YEARS:
        return MUNICIPAL_OFFICES
    if year in GENERAL_ELECTION_YEARS:
        return GENERAL_OFFICES
    return ALL_OFFICES


def _resolve_office(row, year=None):
    allowed = _allowed_offices(year)
    code = _first_field(row, 'CD_CARGO', 'COD_CARGO')
    if code in allowed:
        return allowed[code]
    description = _first_field(row, 'DS_CARGO', 'DESCRICAO_CARGO', 'Cargo').upper()
    return allowed.get(description)


def _extract_municipality(row, office):
    if office not in ('prefeito', 'vereador'):
        return None, None
    mun_name = _first_field(row, 'NM_UE', 'DS_UE', 'DESCRICAO_UE', 'NM_MUNICIPIO', 'Município', 'Municipio', 'Nome da UE') or 'Município não informado'
    mun_code = _first_field(row, 'SG_UE', 'SIGLA_UE', 'CD_MUNICIPIO', 'Número UE', 'Numero UE', 'Sigla da UE') or None
    return mun_name, mun_code


def _normalize_candidacy_text(value):
    text = _clean_field(value)
    return text[:1].upper() + text[1:].lower() if text else None


def _new_candidate_entry(sq, year, office, row, default_result):
    name = _first_field(row, 'NM_CANDIDATO', 'NOME_CANDIDATO', 'Nome candidato') or f'Candidatura {sq}'
    ballot_name = _first_field(row, 'NM_URNA_CANDIDATO', 'NOME_URNA_CANDIDATO') or name
    ballot_number = _first_field(row, 'NR_CANDIDATO', 'NUMERO_CANDIDATO', 'NR_CAND', 'Número candidato', 'Numero candidato')
    party = _first_field(row, 'SG_PARTIDO', 'SIGLA_PARTIDO', 'Sigla Partido', 'Sigla  Partido') or 'Sem partido'
    state = _first_field(row, 'SG_UF', 'UF', 'SG_UE_SUPERIOR') or 'BR'
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
        # Situação do registro (APTO, INAPTO, RENÚNCIA…). Ausente quando a candidatura só consta nas contas.
        'candidacyStatus': _normalize_candidacy_text(_first_field(row, 'DS_SITUACAO_CANDIDATURA')),
        'candidacyDetail': _normalize_candidacy_text(_first_field(row, 'DS_DETALHE_SITUACAO_CAND')),
        'totalRevenueCents': 0,
        'fefcCents': 0,
        'partyFundCents': 0,
        'individualCents': 0,
        'ownResourcesCents': 0,
        'otherRevenueCents': 0,
        'revenueCount': 0,
        'totalExpenseCents': 0,
        'expenseCount': 0,
        '_categories': {}
    }


def normalize_election(
    candidate_rows,
    revenue_rows,
    expense_rows,
    year,
    source_urls,
    fetched_at=None,
    max_vereador_candidates=MAX_VEREADOR_CANDIDATES,
    max_suppliers=MAX_ELECTION_SUPPLIERS,
    mandate_supplier_keys=None
):
    scope = election_scope(year)
    candidates = {}
    for row in candidate_rows:
        office = row.get('_office') or _resolve_office(row, year)
        if not office:
            continue
        sq = _first_field(row, 'SQ_CANDIDATO', 'SEQUENCIAL_CANDIDATO', 'Sequencial Candidato')
        if not sq.isdigit():
            raise ValueError(f'SQ_CANDIDATO inválido no TSE ({year}): {sq!r}')
        entry = _new_candidate_entry(sq, year, office, row, default_result=None)
        existing = candidates.get(sq)
        if existing and existing['elected'] and not entry['elected']:
            continue
        candidates[sq] = entry

    for row in revenue_rows:
        sq = _first_field(row, 'SQ_CANDIDATO', 'SEQUENCIAL_CANDIDATO', 'Sequencial Candidato')
        office = row.get('_office') or _resolve_office(row, year)
        if sq not in candidates:
            if not office or not sq.isdigit():
                continue
            candidates[sq] = _new_candidate_entry(sq, year, office, row, default_result='Prestação de contas sem totalização')
        raw_revenue = _first_field(row, 'VR_RECEITA', 'VALOR_RECEITA', 'Valor receita') or '0'
        try:
            amount = cents(raw_revenue, brazilian=True)
        except ValueError:
            continue
        origin = _first_field(row, 'DS_ORIGEM_RECEITA', 'DESC_ORIGEM_RECEITA', 'TIPO_RECEITA', 'Tipo receita', 'DS_TITULO')
        source = _first_field(row, 'DS_FONTE_RECEITA', 'DS_FONTE_RECURSO', 'FONTE_RECURSO', 'Fonte recurso', 'DS_ESP_RECURSO')
        bucket = _classify_revenue(origin, source)
        candidate = candidates[sq]
        candidate[bucket] += amount
        candidate['totalRevenueCents'] += amount
        candidate['revenueCount'] += 1

    # Compact supplier entry: [cents, count, supplier_name, raw_supplier_id, by_candidate_packed_dict]
    supplier_groups = {}
    unidentified_suppliers = {'cents': 0, 'count': 0}
    elected_vereador_count = sum(1 for c in candidates.values() if c['office'] == 'vereador' and c['elected'])
    skip_unelected_vereador_cats = (
        max_vereador_candidates is not None and elected_vereador_count >= max_vereador_candidates
    )

    for index, row in enumerate(expense_rows, 1):
        sq = _first_field(row, 'SQ_CANDIDATO', 'SEQUENCIAL_CANDIDATO', 'Sequencial Candidato')
        office = row.get('_office') or _resolve_office(row, year)
        if sq not in candidates:
            if not office or not sq.isdigit():
                continue
            candidates[sq] = _new_candidate_entry(sq, year, office, row, default_result='Prestação de contas sem totalização')
        raw_amount = _first_field(row, 'VR_DESPESA_CONTRATADA', 'VR_DESPESA', 'VALOR_DESPESA', 'VR_PAGAMENTO', 'Valor despesa') or '0'
        try:
            amount = cents(raw_amount, brazilian=True)
        except ValueError:
            continue
        candidate = candidates[sq]
        candidate['totalExpenseCents'] += amount
        candidate['expenseCount'] += 1
        if not (skip_unelected_vereador_cats and candidate['office'] == 'vereador' and not candidate['elected']):
            category_name = (
                _first_field(row, 'DS_ORIGEM_DESPESA', 'DS_TIPO_DESPESA', 'DESC_TIPO_DESPESA', 'TIPO_DESPESA', 'Tipo despesa', 'DS_TITULO')
                or 'Despesa não classificada pela fonte'
            )
            cat_stats = candidate['_categories'].get(category_name)
            if cat_stats is None:
                candidate['_categories'][category_name] = [amount, 1]
            else:
                cat_stats[0] += amount
                cat_stats[1] += 1

        raw_supplier_id = _first_field(row, 'NR_CPF_CNPJ_FORNECEDOR', 'CPF_CNPJ_FORNECEDOR', 'CD_CPF_CNPJ_FORNECEDOR', 'CPF/CNPJ do fornecedor')
        key = supplier_key(raw_supplier_id, f'tse:{year}:exp:{index}')
        if key.startswith('unidentified:'):
            unidentified_suppliers['cents'] += amount
            unidentified_suppliers['count'] += 1
            continue

        supplier_name = _first_field(
            row,
            'NM_FORNECEDOR_RFB',
            'NM_FORNECEDOR',
            'NOME_FORNECEDOR',
            'Nome do fornecedor (Receita Federal)',
            'Nome do fornecedor'
        )
        group = supplier_groups.get(key)
        if group is None:
            supplier_groups[key] = [
                amount,
                1,
                supplier_name or 'Fornecedor não informado',
                raw_supplier_id or key,
                {sq: (amount << 20) + 1}
            ]
        else:
            group[0] += amount
            group[1] += 1
            if supplier_name and group[2] == 'Fornecedor não informado':
                group[2] = supplier_name
            by_cand = group[4]
            prev = by_cand.get(sq)
            if prev is None:
                by_cand[sq] = (amount << 20) + 1
            else:
                by_cand[sq] = (((prev >> 20) + amount) << 20) + ((prev & 0xFFFFF) + 1)

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
            {'category': cat_name, 'cents': stats[0], 'count': stats[1]}
            for cat_name, stats in sorted(categories_map.items(), key=lambda item: (-item[1][0], item[0]))[:5]
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

    sorted_supplier_items = sorted(supplier_groups.items(), key=lambda item: (-item[1][0], item[0]))
    mandate_keys = mandate_supplier_keys or set()
    normalized_suppliers = []
    other_identified = {'cents': 0, 'count': 0, 'suppliers': 0}

    for idx, (key, group) in enumerate(sorted_supplier_items):
        if max_suppliers is not None and idx >= max_suppliers and key not in mandate_keys:
            other_identified['cents'] += group[0]
            other_identified['count'] += group[1]
            other_identified['suppliers'] += 1
            continue
        by_cand = group[4]
        offices_set = set()
        states_set = set()
        parties_set = set()
        for sq in by_cand:
            cand = candidates[sq]
            offices_set.add(cand['office'])
            states_set.add(cand['state'])
            parties_set.add(cand['party'])
        top_cands = []
        for sq, packed in sorted(by_cand.items(), key=lambda item: (-(item[1] >> 20), item[0]))[:6]:
            cand = candidates[sq]
            top_cands.append({
                'id': cand['id'],
                'ballotName': cand['ballotName'],
                'party': cand['party'],
                'state': cand['state'],
                'municipality': cand['municipality'],
                'office': cand['office'],
                'cents': packed >> 20,
                'count': packed & 0xFFFFF
            })
        normalized_suppliers.append({
            'supplierKey': key,
            'supplier': group[2],
            'supplierId': group[3],
            'year': year,
            'cents': group[0],
            'count': group[1],
            'candidacyCount': len(by_cand),
            'offices': sorted(offices_set),
            'states': sorted(states_set),
            'parties': sorted(parties_set),
            'topCandidates': top_cands
        })

    return {
        'year': year,
        'scope': scope,
        'collectedOffices': sorted(set(_allowed_offices(year).values())),
        'status': 'collected',
        'reason': None,
        'fetchedAt': fetched_at,
        'sourceUrls': source_urls,
        'candidates': normalized_candidates,
        'aggregatedCandidates': aggregated_candidates,
        'parties': normalized_parties,
        'suppliers': {
            'unidentified': unidentified_suppliers,
            'otherIdentified': other_identified,
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
            'otherIdentified': {'cents': 0, 'count': 0, 'suppliers': 0},
            'rows': []
        }
    }


_KEEP_COLUMNS = frozenset({
    'CD_CARGO', 'COD_CARGO', 'DS_CARGO', 'DESCRICAO_CARGO', 'Cargo',
    'SQ_CANDIDATO', 'SEQUENCIAL_CANDIDATO', 'Sequencial Candidato',
    'NR_CPF_CANDIDATO', 'CPF_CANDIDATO', 'CPF candidato', 'CPF do candidato',
    'NM_CANDIDATO', 'NOME_CANDIDATO', 'Nome candidato',
    'NM_URNA_CANDIDATO', 'NOME_URNA_CANDIDATO',
    'NR_CANDIDATO', 'NUMERO_CANDIDATO', 'NR_CAND', 'Número candidato', 'Numero candidato',
    'SG_PARTIDO', 'SIGLA_PARTIDO', 'Sigla Partido', 'Sigla  Partido',
    'SG_UF', 'UF', 'SG_UE_SUPERIOR',
    'NM_UE', 'DS_UE', 'DESCRICAO_UE', 'NM_MUNICIPIO', 'Município', 'Municipio', 'Nome da UE',
    'SG_UE', 'SIGLA_UE', 'CD_MUNICIPIO', 'Número UE', 'Numero UE', 'Sigla da UE',
    'DS_SIT_TOT_TURNO', 'DESC_SIT_TOT_TURNO', 'DESC_SIT_CAND_TOT',
    'DS_SITUACAO_CANDIDATURA', 'DS_DETALHE_SITUACAO_CAND',
    'VR_RECEITA', 'VALOR_RECEITA', 'Valor receita',
    'DS_ORIGEM_RECEITA', 'DESC_ORIGEM_RECEITA', 'TIPO_RECEITA', 'Tipo receita', 'DS_TITULO',
    'DS_FONTE_RECEITA', 'DS_FONTE_RECURSO', 'FONTE_RECURSO', 'Fonte recurso', 'DS_ESP_RECURSO',
    'VR_DESPESA_CONTRATADA', 'VR_DESPESA', 'VALOR_DESPESA', 'VR_PAGAMENTO', 'Valor despesa',
    'DS_ORIGEM_DESPESA', 'DS_TIPO_DESPESA', 'DESC_TIPO_DESPESA', 'TIPO_DESPESA', 'Tipo despesa',
    'NR_CPF_CNPJ_FORNECEDOR', 'CPF_CNPJ_FORNECEDOR', 'CD_CPF_CNPJ_FORNECEDOR', 'CPF/CNPJ do fornecedor',
    'NM_FORNECEDOR_RFB', 'NM_FORNECEDOR', 'NOME_FORNECEDOR', 'Nome do fornecedor (Receita Federal)', 'Nome do fornecedor'
})


def _iter_filtered_csv_lines(line_iterable, year=None):
    allowed = _allowed_offices(year)
    header = None
    keep_indices = ()
    cargo_code_idx = -1
    cargo_desc_idx = -1
    cleaned_lines = (raw.replace('\x00', '') for raw in line_iterable)
    for row in csv.reader(cleaned_lines, delimiter=';'):
        if not row:
            continue
        if header is None:
            header = [col.strip() for col in row]
            keep_list = []
            for idx, col in enumerate(header):
                col_upper = col.upper()
                if col_upper in ('CD_CARGO', 'COD_CARGO'):
                    cargo_code_idx = idx
                elif col_upper in ('DS_CARGO', 'DESCRICAO_CARGO', 'CARGO'):
                    cargo_desc_idx = idx
                if col in _KEEP_COLUMNS:
                    keep_list.append((idx, col))
            keep_indices = tuple(keep_list)
            continue
        row_len = len(row)
        office = None
        if 0 <= cargo_code_idx < row_len:
            office = allowed.get(row[cargo_code_idx].strip())
        if not office and 0 <= cargo_desc_idx < row_len:
            office = allowed.get(row[cargo_desc_idx].strip().upper())
        if not office:
            continue
        row_dict = {'_office': office}
        for idx, col in keep_indices:
            if idx < row_len:
                row_dict[col] = row[idx]
        yield row_dict


def _select_zip_filenames(archive_names, prefixes):
    if isinstance(prefixes, str):
        prefixes = (prefixes,)
    valid_names = [
        name for name in archive_names
        if name.lower().endswith(('.csv', '.txt'))
        and 'leiame' not in name.lower()
        and 'notas' not in name.lower()
        and 'originario' not in name.lower()
        and 'pagas' not in name.lower()
        and 'comite' not in name.lower()
        and 'partido' not in name.lower()
    ]
    matched_names = []
    for prefix in prefixes:
        p_lower = prefix.lower()
        p_compact = p_lower.replace('_', '')
        matched_names = [
            name for name in valid_names
            if p_lower in name.lower() or p_compact in name.lower().replace('_', '')
        ]
        if matched_names:
            break
    if not matched_names:
        raise ValueError(f'CSV {prefixes!r} não encontrado no pacote TSE')
    brasil_files = [name for name in matched_names if 'brasil' in name.lower()]
    return sorted(brasil_files or matched_names)


def _read_csv_from_zip(raw_bytes, prefixes, year=None):
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        selected = _select_zip_filenames(archive.namelist(), prefixes)
        for filename in selected:
            with archive.open(filename) as raw:
                text_stream = io.TextIOWrapper(raw, encoding='latin-1', errors='replace')
                yield from _iter_filtered_csv_lines(text_stream, year=year)


def _http_range_get(url, start_byte, end_byte, timeout=90):
    headers = {
        'User-Agent': 'PercursoPublico/1.0 (public financial data)',
        'Accept': '*/*',
        'Range': f'bytes={start_byte}-{end_byte}'
    }
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as resp:
                return resp.read()
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
        except (IncompleteRead, RemoteDisconnected, URLError, TimeoutError):
            if attempt == 3:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError(f'Falha na leitura parcial de {url}')


def _http_head_meta(url, timeout=45):
    headers = {'User-Agent': 'PercursoPublico/1.0 (public financial data)', 'Accept': '*/*'}
    for attempt in range(4):
        try:
            with urlopen(Request(url, method='HEAD', headers=headers), timeout=timeout) as resp:
                size = int(resp.headers.get('Content-Length') or 0)
                accept_ranges = (resp.headers.get('Accept-Ranges') or '').lower() == 'bytes'
                etag = resp.headers.get('ETag')
                last_modified = resp.headers.get('Last-Modified')
                return {
                    'url': url,
                    'size': size,
                    'acceptRanges': accept_ranges,
                    'etag': etag,
                    'lastModified': last_modified,
                    'fetchedAt': datetime.now(timezone.utc).isoformat()
                }
        except HTTPError as exc:
            if exc.code == 404:
                raise
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
        except (IncompleteRead, RemoteDisconnected, URLError, TimeoutError):
            if attempt == 3:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError(f'Falha ao consultar cabeçalhos de {url}')


def _fetch_remote_zip_directory(url, size):
    tail_size = min(size, 256 * 1024)
    tail = _http_range_get(url, size - tail_size, size - 1)
    eocd_pos = tail.rfind(b'PK\x05\x06')
    if eocd_pos == -1:
        raise ValueError(f'Diretório central ZIP não encontrado em {url}')
    cd_size, cd_offset = struct.unpack('<II', tail[eocd_pos + 12:eocd_pos + 20])
    if cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
        loc_pos = eocd_pos - 20
        if loc_pos >= 0 and tail[loc_pos:loc_pos + 4] == b'PK\x06\x07':
            z64_eocd_offset = struct.unpack('<Q', tail[loc_pos + 8:loc_pos + 16])[0]
            rel = z64_eocd_offset - (size - tail_size)
            if rel >= 0:
                z64_eocd = tail[rel:rel + 56]
            else:
                z64_eocd = _http_range_get(url, z64_eocd_offset, z64_eocd_offset + 55)
            cd_size, cd_offset = struct.unpack('<QQ', z64_eocd[40:56])
    cd = _http_range_get(url, cd_offset, cd_offset + cd_size - 1)
    pos = 0
    entries = {}
    while pos < len(cd) and cd[pos:pos + 4] == b'PK\x01\x02':
        comp_method = struct.unpack('<H', cd[pos + 10:pos + 12])[0]
        crc32_val, comp_size, uncomp_size = struct.unpack('<III', cd[pos + 16:pos + 28])
        fname_len, extra_len, comment_len = struct.unpack('<HHH', cd[pos + 28:pos + 34])
        local_offset = struct.unpack('<I', cd[pos + 42:pos + 46])[0]
        fname = cd[pos + 46:pos + 46 + fname_len].decode('latin-1', errors='replace')
        extra = cd[pos + 46 + fname_len:pos + 46 + fname_len + extra_len]
        if comp_size == 0xFFFFFFFF or uncomp_size == 0xFFFFFFFF or local_offset == 0xFFFFFFFF:
            ep = 0
            while ep + 4 <= len(extra):
                header_id, data_size = struct.unpack('<HH', extra[ep:ep + 4])
                if header_id == 0x0001:
                    edata = extra[ep + 4:ep + 4 + data_size]
                    idx = 0
                    if uncomp_size == 0xFFFFFFFF:
                        uncomp_size = struct.unpack('<Q', edata[idx:idx + 8])[0]
                        idx += 8
                    if comp_size == 0xFFFFFFFF:
                        comp_size = struct.unpack('<Q', edata[idx:idx + 8])[0]
                        idx += 8
                    if local_offset == 0xFFFFFFFF:
                        local_offset = struct.unpack('<Q', edata[idx:idx + 8])[0]
                    break
                ep += 4 + data_size
        entries[fname] = {
            'method': comp_method,
            'crc32': crc32_val,
            'compSize': comp_size,
            'uncompSize': uncomp_size,
            'localOffset': local_offset
        }
        pos += 46 + fname_len + extra_len + comment_len
    return entries


def _stream_remote_zip_entry_lines(url, entry):
    local_offset = entry['localOffset']
    comp_size = entry['compSize']
    method = entry['method']
    lheader = _http_range_get(url, local_offset, local_offset + 29)
    if lheader[:4] != b'PK\x03\x04':
        raise ValueError(f'Cabeçalho local ZIP inválido em {url}')
    lf_len, le_len = struct.unpack('<HH', lheader[26:30])
    data_start = local_offset + 30 + lf_len + le_len
    data_end = data_start + comp_size - 1

    decomp = zlib.decompressobj(-zlib.MAX_WBITS) if method == 8 else None
    cursor = data_start
    window_bytes = 16 * 1024 * 1024  # 16 MB range windows for resilient streaming
    text_buf = ''

    while cursor <= data_end:
        chunk_end = min(cursor + window_bytes - 1, data_end)
        for attempt in range(4):
            headers = {
                'User-Agent': 'PercursoPublico/1.0 (public financial data)',
                'Accept': '*/*',
                'Range': f'bytes={cursor}-{chunk_end}'
            }
            try:
                with urlopen(Request(url, headers=headers), timeout=90) as resp:
                    while cursor <= chunk_end:
                        block = resp.read(65536)
                        if not block:
                            break
                        cursor += len(block)
                        raw_bytes = decomp.decompress(block) if decomp else block
                        if raw_bytes:
                            text_buf += raw_bytes.decode('latin-1', errors='replace')
                            if '\n' in text_buf:
                                lines = text_buf.split('\n')
                                text_buf = lines.pop()
                                for line in lines:
                                    yield line
                break
            except (HTTPError, IncompleteRead, RemoteDisconnected, URLError, TimeoutError) as exc:
                if isinstance(exc, HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                    raise
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)

    if decomp:
        tail_bytes = decomp.flush()
        if tail_bytes:
            text_buf += tail_bytes.decode('latin-1', errors='replace')
    if text_buf:
        for line in text_buf.split('\n'):
            if line:
                yield line


def _stream_csv_from_remote_zip(url, entries, prefixes, year=None):
    selected = _select_zip_filenames(list(entries.keys()), prefixes)
    for filename in selected:
        line_gen = _stream_remote_zip_entry_lines(url, entries[filename])
        yield from _iter_filtered_csv_lines(line_gen, year=year)


def _record_source_metadata(client, url, meta, entries, selected_prefixes):
    fingerprint_payload = json.dumps({
        'url': url,
        'size': meta.get('size'),
        'etag': meta.get('etag'),
        'lastModified': meta.get('lastModified'),
        'crcs': [
            (fname, entries[fname]['crc32'], entries[fname]['compSize'])
            for prefixes in selected_prefixes
            for fname in _select_zip_filenames(list(entries.keys()), prefixes)
        ]
    }, sort_keys=True).encode('utf-8')
    client.sources[url] = {
        'url': url,
        'fetchedAt': meta['fetchedAt'],
        'sha256': hashlib.sha256(fingerprint_payload).hexdigest(),
        'etag': meta.get('etag'),
        'lastModified': meta.get('lastModified')
    }


def collect_election_year(client, year, mandate_supplier_keys=None):
    cand_url = candidates_url(year)
    acc_url = accounts_url(year)
    cache_days = client.historical_cache_days(year)

    cache_tag = MUNICIPAL_CACHE_SCHEMA_TAG if year in MUNICIPAL_ELECTION_YEARS else CACHE_SCHEMA_TAG
    cache_file = client.cache / f'tse-election-{year}-{cache_tag}.json.gz'
    cache_meta_file = client.cache / f'tse-election-{year}-{cache_tag}.meta.json'
    if cache_file.exists() and cache_meta_file.exists():
        try:
            meta = json.loads(cache_meta_file.read_text(encoding='utf-8'))
            fresh = (
                cache_days > 0
                and not client.review_history
                and datetime.fromisoformat(meta['fetchedAt']) > datetime.now(timezone.utc) - timedelta(days=cache_days)
            )
            if client.offline or client.reuse_cache or fresh:
                cached_data = json.loads(gzip.decompress(cache_file.read_bytes()).decode('utf-8'))
                for src in meta.get('sources', []):
                    client.sources[src['url']] = {**src, 'cacheReused': True}
                return cached_data
        except (ValueError, KeyError, OSError):
            if client.offline:
                raise

    # Se o cliente for um mock de teste ou se o arquivo bruto já estiver no cache local do Client, usar client.get
    cand_cache_key = hashlib.sha256(cand_url.encode()).hexdigest()
    if client.offline or (client.cache / cand_cache_key).exists() or type(client).get is not getattr(__import__('pipeline.http', fromlist=['Client']).Client, 'get'):
        try:
            cand_bytes = client.get(cand_url, cache_days=cache_days)
            acc_bytes = None
            last_exc = None
            for candidate_acc_url in accounts_candidate_urls(year):
                try:
                    acc_bytes = client.get(candidate_acc_url, cache_days=cache_days)
                    acc_url = candidate_acc_url
                    break
                except HTTPError as exc:
                    if exc.code != 404:
                        raise
                    last_exc = exc
            if acc_bytes is None:
                return unavailable_election(
                    year,
                    f'Pacote de prestação de contas eleitorais {year} ainda não disponível ou inacessível na origem ({last_exc.__class__.__name__}).'
                )
            candidate_rows = _read_csv_from_zip(cand_bytes, ('consulta_cand',), year=year)
            revenue_rows = _read_csv_from_zip(acc_bytes, ('receitas_candidatos',), year=year)
            expense_rows = _read_csv_from_zip(acc_bytes, ('despesas_contratadas_candidatos', 'despesas_candidatos'), year=year)
            fetched_at = client.sources.get(acc_url, {}).get('fetchedAt')
            return normalize_election(
                candidate_rows,
                revenue_rows,
                expense_rows,
                year,
                {'candidates': cand_url, 'accounts': acc_url},
                fetched_at=fetched_at,
                mandate_supplier_keys=mandate_supplier_keys
            )
        except HTTPError as exc:
            if exc.code != 404:
                raise
            return unavailable_election(
                year,
                f'Pacote de prestação de contas eleitorais {year} ainda não disponível ou inacessível na origem ({exc.__class__.__name__}).'
            )

    # Coleta via streaming HTTP Range do diretório central ZIP (sem baixar 500MB–1.3GB para a RAM/disco)
    try:
        cand_meta = _http_head_meta(cand_url)
        cand_entries = _fetch_remote_zip_directory(cand_url, cand_meta['size'])
    except HTTPError as exc:
        if exc.code != 404:
            raise
        return unavailable_election(
            year,
            f'Pacote de candidaturas eleitorais {year} ainda não disponível ou inacessível na origem ({exc.__class__.__name__}).'
        )

    acc_meta = None
    acc_entries = None
    last_exc = None
    for candidate_acc_url in accounts_candidate_urls(year):
        try:
            acc_meta = _http_head_meta(candidate_acc_url)
            acc_entries = _fetch_remote_zip_directory(candidate_acc_url, acc_meta['size'])
            acc_url = candidate_acc_url
            break
        except HTTPError as exc:
            if exc.code != 404:
                raise
            last_exc = exc
            continue

    if acc_meta is None or acc_entries is None:
        return unavailable_election(
            year,
            f'Pacote de prestação de contas eleitorais {year} ainda não disponível ou inacessível na origem ({last_exc.__class__.__name__}).'
        )

    try:
        candidate_rows = _stream_csv_from_remote_zip(cand_url, cand_entries, ('consulta_cand',), year=year)
        revenue_rows = _stream_csv_from_remote_zip(acc_url, acc_entries, ('receitas_candidatos',), year=year)
        expense_rows = _stream_csv_from_remote_zip(
            acc_url,
            acc_entries,
            ('despesas_contratadas_candidatos', 'despesas_candidatos'),
            year=year
        )
        result = normalize_election(
            candidate_rows,
            revenue_rows,
            expense_rows,
            year,
            {'candidates': cand_url, 'accounts': acc_url},
            fetched_at=acc_meta['fetchedAt'],
            mandate_supplier_keys=mandate_supplier_keys
        )
        _record_source_metadata(client, cand_url, cand_meta, cand_entries, (('consulta_cand',),))
        _record_source_metadata(
            client,
            acc_url,
            acc_meta,
            acc_entries,
            (('receitas_candidatos',), ('despesas_contratadas_candidatos', 'despesas_candidatos'))
        )
        # Persistir apenas o pacote normalizado compacto (~300 KB) no cache do pipeline
        tmp_cache = cache_file.with_suffix('.tmp')
        tmp_cache.write_bytes(gzip.compress(json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), compresslevel=6))
        os.replace(tmp_cache, cache_file)
        cache_meta_file.write_text(json.dumps({
            'year': year,
            'fetchedAt': acc_meta['fetchedAt'],
            'sources': [client.sources[cand_url], client.sources[acc_url]]
        }), encoding='utf-8')
        return result
    except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError, zlib.error):
        # Falha de leitura/normalização impede a publicação; somente 404 é ausência.
        raise

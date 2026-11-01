from collections import Counter
from pipeline.normalize.common import MAX_SAFE_INTEGER, supplier_key


def safe_money(value):
    if isinstance(value, bool) or not isinstance(value, int) or abs(value) > MAX_SAFE_INTEGER:
        raise ValueError('Centavos fora do contrato')


def validate_suppliers(records, suppliers_summary, members, year):
    if not isinstance(suppliers_summary, dict) or suppliers_summary.get('year') != year:
        raise ValueError('Agregado anual de fornecedores inválido')
    detail_identified_totals, detail_identified_counts = Counter(), Counter()
    detail_unidentified_totals, detail_unidentified_counts = Counter(), Counter()
    for row in records:
        key = supplier_key(row.get('supplierId'), row['id'])
        if key.startswith('unidentified:'):
            u_key = (row['memberId'], row['year'])
            detail_unidentified_totals[u_key] += row['cents']
            detail_unidentified_counts[u_key] += 1
        else:
            i_key = (key, row['memberId'], row['year'])
            detail_identified_totals[i_key] += row['cents']
            detail_identified_counts[i_key] += 1

    summary_identified_totals, summary_identified_counts = Counter(), Counter()
    seen_identified = set()
    for row in suppliers_summary.get('rows', []):
        safe_money(row['cents'])
        key = row.get('supplierKey') or ''
        if len(key) not in (11, 14) or not key.isdigit() or int(key) <= 7:
            raise ValueError(f'Chave de fornecedor inválida no agregado: {key}')
        if row.get('memberId') not in members or row.get('year') != year or row.get('count', 0) < 1:
            raise ValueError('Linha de fornecedor com parlamentar, ano ou contagem inválidos')
        i_key = (key, row['memberId'], row['year'])
        if i_key in seen_identified:
            raise ValueError(f'Fornecedor duplicado para o mesmo parlamentar/ano: {i_key}')
        seen_identified.add(i_key)
        summary_identified_totals[i_key] += row['cents']
        summary_identified_counts[i_key] += row['count']

    summary_unidentified_totals, summary_unidentified_counts = Counter(), Counter()
    seen_unidentified = set()
    for row in suppliers_summary.get('unidentified', []):
        safe_money(row['cents'])
        if row.get('memberId') not in members or row.get('year') != year or row.get('count', 0) < 1:
            raise ValueError('Total sem identificação de fornecedor inválido')
        u_key = (row['memberId'], row['year'])
        if u_key in seen_unidentified:
            raise ValueError(f'Total sem identificação duplicado: {u_key}')
        seen_unidentified.add(u_key)
        summary_unidentified_totals[u_key] += row['cents']
        summary_unidentified_counts[u_key] += row['count']

    if (dict(detail_identified_totals) != dict(summary_identified_totals)
            or dict(detail_identified_counts) != dict(summary_identified_counts)
            or dict(detail_unidentified_totals) != dict(summary_unidentified_totals)
            or dict(detail_unidentified_counts) != dict(summary_unidentified_counts)):
        raise ValueError('Agregado de fornecedores não reconcilia com detalhes')


ELECTION_YEARS = (2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024, 2026)
MUNICIPAL_ELECTION_YEARS = (2008, 2012, 2016, 2020, 2024)


def validate_election(election):
    if not isinstance(election, dict) or election.get('year') not in ELECTION_YEARS:
        raise ValueError('Arquivo eleitoral inválido ou ano fora do escopo')
    year = election['year']
    expected_scope = 'municipal' if year in MUNICIPAL_ELECTION_YEARS else 'geral'
    scope = election.get('scope', expected_scope)
    if scope != expected_scope:
        raise ValueError(f'Escopo eleitoral inválido para {year}: {scope}')
    allowed_offices = ('prefeito', 'vereador') if scope == 'municipal' else ('deputado_federal', 'senador')
    status = election.get('status')
    if status not in ('collected', 'unavailable'):
        raise ValueError('Status eleitoral inválido')
    candidates = election.get('candidates', [])
    aggregated_candidates = election.get('aggregatedCandidates', [])
    parties = election.get('parties', [])
    suppliers = election.get('suppliers', {})
    unidentified = suppliers.get('unidentified', {})
    supplier_rows = suppliers.get('rows', [])
    if status == 'unavailable':
        if candidates or aggregated_candidates or parties or supplier_rows or unidentified != {'cents': 0, 'count': 0}:
            raise ValueError('Eleição indisponível não pode publicar totais parciais ou zerados como coletados')
        return

    seen_candidates = set()
    party_Rollup = {}
    for cand in candidates:
        sq = str(cand.get('sqCandidato') or '')
        expected_id = f'tse:{year}:{sq}'
        if not sq.isdigit() or cand.get('id') != expected_id or cand.get('year') != year:
            raise ValueError(f'Identificador de candidatura TSE inválido: {cand.get("id")}')
        if expected_id in seen_candidates:
            raise ValueError(f'Candidatura duplicada no TSE: {expected_id}')
        seen_candidates.add(expected_id)
        if cand.get('office') not in allowed_offices:
            raise ValueError(f'Cargo eleitoral fora do escopo de {year}: {cand.get("office")}')
        if scope == 'municipal' and not cand.get('municipality'):
            raise ValueError(f'Candidatura municipal sem município identificado: {expected_id}')
        for field in (
            'totalRevenueCents', 'fefcCents', 'partyFundCents',
            'individualCents', 'ownResourcesCents', 'otherRevenueCents', 'totalExpenseCents'
        ):
            safe_money(cand[field])
        revenue_parts = (
            cand['fefcCents'] + cand['partyFundCents'] + cand['individualCents']
            + cand['ownResourcesCents'] + cand['otherRevenueCents']
        )
        if revenue_parts != cand['totalRevenueCents']:
            raise ValueError(f'Receitas por fonte não reconciliam na candidatura {expected_id}')
        p_key = (cand['party'], cand['office'])
        group = party_Rollup.setdefault(p_key, {
            'candidacyCount': 0, 'electedCount': 0,
            'totalRevenueCents': 0, 'fefcCents': 0, 'partyFundCents': 0,
            'individualCents': 0, 'ownResourcesCents': 0, 'otherRevenueCents': 0,
            'totalExpenseCents': 0, 'expenseCount': 0
        })
        group['candidacyCount'] += 1
        if cand.get('elected'):
            group['electedCount'] += 1
        for field in (
            'totalRevenueCents', 'fefcCents', 'partyFundCents',
            'individualCents', 'ownResourcesCents', 'otherRevenueCents',
            'totalExpenseCents', 'expenseCount'
        ):
            group[field] += cand[field]

    for agg in aggregated_candidates:
        if agg.get('year') != year or agg.get('office') != 'vereador' or scope != 'municipal':
            raise ValueError('Agregado complementar de candidaturas inválido')
        if agg.get('candidacyCount', 0) < 1:
            raise ValueError('Agregado complementar sem candidaturas')
        for field in (
            'totalRevenueCents', 'fefcCents', 'partyFundCents',
            'individualCents', 'ownResourcesCents', 'otherRevenueCents', 'totalExpenseCents'
        ):
            safe_money(agg[field])
        revenue_parts = (
            agg['fefcCents'] + agg['partyFundCents'] + agg['individualCents']
            + agg['ownResourcesCents'] + agg['otherRevenueCents']
        )
        if revenue_parts != agg['totalRevenueCents']:
            raise ValueError('Receitas por fonte não reconciliam no agregado complementar')
        p_key = (agg['party'], agg['office'])
        group = party_Rollup.setdefault(p_key, {
            'candidacyCount': 0, 'electedCount': 0,
            'totalRevenueCents': 0, 'fefcCents': 0, 'partyFundCents': 0,
            'individualCents': 0, 'ownResourcesCents': 0, 'otherRevenueCents': 0,
            'totalExpenseCents': 0, 'expenseCount': 0
        })
        group['candidacyCount'] += agg['candidacyCount']
        group['electedCount'] += agg['electedCount']
        for field in (
            'totalRevenueCents', 'fefcCents', 'partyFundCents',
            'individualCents', 'ownResourcesCents', 'otherRevenueCents',
            'totalExpenseCents', 'expenseCount'
        ):
            group[field] += agg[field]

    seen_parties = set()
    party_summary_map = {}
    for row in parties:
        p_key = (row.get('party'), row.get('office'))
        if p_key in seen_parties or row.get('year') != year or row.get('office') not in allowed_offices:
            raise ValueError(f'Resumo partidário eleitoral duplicado ou inválido: {p_key}')
        seen_parties.add(p_key)
        for field in (
            'totalRevenueCents', 'fefcCents', 'partyFundCents',
            'individualCents', 'ownResourcesCents', 'otherRevenueCents', 'totalExpenseCents'
        ):
            safe_money(row[field])
        party_summary_map[p_key] = {key: row[key] for key in party_Rollup.get(p_key, {})}

    if party_Rollup != party_summary_map:
        raise ValueError('Agregado partidário do TSE não reconcilia com as candidaturas')

    seen_suppliers = set()
    supplier_cents = 0
    supplier_count = 0
    for row in supplier_rows:
        safe_money(row['cents'])
        key = row.get('supplierKey') or ''
        if len(key) not in (11, 14) or not key.isdigit() or int(key) <= 7:
            raise ValueError(f'Chave de fornecedor eleitoral inválida: {key}')
        if key in seen_suppliers or row.get('year') != year or row.get('count', 0) < 1:
            raise ValueError(f'Fornecedor eleitoral duplicado ou inválido: {key}')
        seen_suppliers.add(key)
        supplier_cents += row['cents']
        supplier_count += row['count']

    safe_money(unidentified.get('cents', 0))
    total_cand_expenses = (
        sum(cand['totalExpenseCents'] for cand in candidates)
        + sum(agg['totalExpenseCents'] for agg in aggregated_candidates)
    )
    total_cand_expense_count = (
        sum(cand['expenseCount'] for cand in candidates)
        + sum(agg['expenseCount'] for agg in aggregated_candidates)
    )
    if (supplier_cents + unidentified.get('cents', 0) != total_cand_expenses
            or supplier_count + unidentified.get('count', 0) != total_cand_expense_count):
        raise ValueError('Fornecedores de campanha não reconciliam com o total de despesas eleitorais')


def validate_election(election):
    if not isinstance(election, dict) or election.get('year') not in ELECTION_YEARS:
        raise ValueError('Arquivo eleitoral inválido ou ano fora do escopo')
    year = election['year']
    expected_scope = 'municipal' if year in MUNICIPAL_ELECTION_YEARS else 'geral'
    scope = election.get('scope', expected_scope)
    if scope != expected_scope:
        raise ValueError(f'Escopo eleitoral inválido para {year}: {scope}')
    allowed_offices = ('prefeito', 'vereador') if scope == 'municipal' else ('deputado_federal', 'senador')
    status = election.get('status')
    if status not in ('collected', 'unavailable'):
        raise ValueError('Status eleitoral inválido')
    candidates = election.get('candidates', [])
    aggregated_candidates = election.get('aggregatedCandidates', [])
    parties = election.get('parties', [])
    suppliers = election.get('suppliers', {})
    unidentified = suppliers.get('unidentified', {})
    supplier_rows = suppliers.get('rows', [])
    if status == 'unavailable':
        if candidates or aggregated_candidates or parties or supplier_rows or unidentified != {'cents': 0, 'count': 0}:
            raise ValueError('Eleição indisponível não pode publicar totais parciais ou zerados como coletados')
        return

    seen_candidates = set()
    party_Rollup = {}
    for cand in candidates:
        sq = str(cand.get('sqCandidato') or '')
        expected_id = f'tse:{year}:{sq}'
        if not sq.isdigit() or cand.get('id') != expected_id or cand.get('year') != year:
            raise ValueError(f'Identificador de candidatura TSE inválido: {cand.get("id")}')
        if expected_id in seen_candidates:
            raise ValueError(f'Candidatura duplicada no TSE: {expected_id}')
        seen_candidates.add(expected_id)
        if cand.get('office') not in allowed_offices:
            raise ValueError(f'Cargo eleitoral fora do escopo de {year}: {cand.get("office")}')
        if scope == 'municipal' and not cand.get('municipality'):
            raise ValueError(f'Candidatura municipal sem município identificado: {expected_id}')
        for field in (
            'totalRevenueCents', 'fefcCents', 'partyFundCents',
            'individualCents', 'ownResourcesCents', 'otherRevenueCents', 'totalExpenseCents'
        ):
            safe_money(cand[field])
        revenue_parts = (
            cand['fefcCents'] + cand['partyFundCents'] + cand['individualCents']
            + cand['ownResourcesCents'] + cand['otherRevenueCents']
        )
        if revenue_parts != cand['totalRevenueCents']:
            raise ValueError(f'Receitas por fonte não reconciliam na candidatura {expected_id}')
        p_key = (cand['party'], cand['office'])
        group = party_Rollup.setdefault(p_key, {
            'candidacyCount': 0, 'electedCount': 0,
            'totalRevenueCents': 0, 'fefcCents': 0, 'partyFundCents': 0,
            'individualCents': 0, 'ownResourcesCents': 0, 'otherRevenueCents': 0,
            'totalExpenseCents': 0, 'expenseCount': 0
        })
        group['candidacyCount'] += 1
        if cand.get('elected'):
            group['electedCount'] += 1
        for field in (
            'totalRevenueCents', 'fefcCents', 'partyFundCents',
            'individualCents', 'ownResourcesCents', 'otherRevenueCents',
            'totalExpenseCents', 'expenseCount'
        ):
            group[field] += cand[field]

    for agg in aggregated_candidates:
        if agg.get('year') != year or agg.get('office') != 'vereador' or scope != 'municipal':
            raise ValueError('Agregado complementar de candidaturas inválido')
        if agg.get('candidacyCount', 0) < 1:
            raise ValueError('Agregado complementar sem candidaturas')
        for field in (
            'totalRevenueCents', 'fefcCents', 'partyFundCents',
            'individualCents', 'ownResourcesCents', 'otherRevenueCents', 'totalExpenseCents'
        ):
            safe_money(agg[field])
        revenue_parts = (
            agg['fefcCents'] + agg['partyFundCents'] + agg['individualCents']
            + agg['ownResourcesCents'] + agg['otherRevenueCents']
        )
        if revenue_parts != agg['totalRevenueCents']:
            raise ValueError('Receitas por fonte não reconciliam no agregado complementar')
        p_key = (agg['party'], agg['office'])
        group = party_Rollup.setdefault(p_key, {
            'candidacyCount': 0, 'electedCount': 0,
            'totalRevenueCents': 0, 'fefcCents': 0, 'partyFundCents': 0,
            'individualCents': 0, 'ownResourcesCents': 0, 'otherRevenueCents': 0,
            'totalExpenseCents': 0, 'expenseCount': 0
        })
        group['candidacyCount'] += agg['candidacyCount']
        group['electedCount'] += agg['electedCount']
        for field in (
            'totalRevenueCents', 'fefcCents', 'partyFundCents',
            'individualCents', 'ownResourcesCents', 'otherRevenueCents',
            'totalExpenseCents', 'expenseCount'
        ):
            group[field] += agg[field]

    seen_parties = set()
    party_summary_map = {}
    for row in parties:
        p_key = (row.get('party'), row.get('office'))
        if p_key in seen_parties or row.get('year') != year or row.get('office') not in allowed_offices:
            raise ValueError(f'Resumo partidário eleitoral duplicado ou inválido: {p_key}')
        seen_parties.add(p_key)
        for field in (
            'totalRevenueCents', 'fefcCents', 'partyFundCents',
            'individualCents', 'ownResourcesCents', 'otherRevenueCents', 'totalExpenseCents'
        ):
            safe_money(row[field])
        party_summary_map[p_key] = {key: row[key] for key in party_Rollup.get(p_key, {})}

    if party_Rollup != party_summary_map:
        raise ValueError('Agregado partidário do TSE não reconcilia com as candidaturas')

    seen_suppliers = set()
    supplier_cents = 0
    supplier_count = 0
    for row in supplier_rows:
        safe_money(row['cents'])
        key = row.get('supplierKey') or ''
        if len(key) not in (11, 14) or not key.isdigit() or int(key) <= 7:
            raise ValueError(f'Chave de fornecedor eleitoral inválida: {key}')
        if key in seen_suppliers or row.get('year') != year or row.get('count', 0) < 1:
            raise ValueError(f'Fornecedor eleitoral duplicado ou inválido: {key}')
        seen_suppliers.add(key)
        supplier_cents += row['cents']
        supplier_count += row['count']

    safe_money(unidentified.get('cents', 0))
    total_cand_expenses = (
        sum(cand['totalExpenseCents'] for cand in candidates)
        + sum(agg['totalExpenseCents'] for agg in aggregated_candidates)
    )
    total_cand_expense_count = (
        sum(cand['expenseCount'] for cand in candidates)
        + sum(agg['expenseCount'] for agg in aggregated_candidates)
    )
    if (supplier_cents + unidentified.get('cents', 0) != total_cand_expenses
            or supplier_count + unidentified.get('count', 0) != total_cand_expense_count):
        raise ValueError('Fornecedores de campanha não reconciliam com o total de despesas eleitorais')


def validate(records, summary, members):
    seen = set()
    detail_totals, summary_totals = Counter(), Counter()
    detail_counts, summary_counts = Counter(), Counter()
    for row in records:
        if row['id'] in seen:
            raise ValueError(f"Identificador de despesa duplicado: {row['id']}")
        seen.add(row['id'])
        if row['memberId'] not in members or not row['id'].startswith(row['memberId'].split(':')[0] + ':'):
            raise ValueError('Junção inválida de parlamentar/Casa')
        if row['month'] not in range(1, 13) or not row['category'] or not row['sourceUrl']:
            raise ValueError('Registro sem competência, categoria ou origem')
        chamber = members[row['memberId']].get('chamber')
        if chamber == 'deputados' and not str(row.get('portalUrl') or '').startswith(
            'https://www.camara.leg.br/cota-parlamentar/sumarizado?'
        ):
            raise ValueError('Despesa da Câmara sem link para consulta oficial')
        if chamber == 'senadores' and row.get('portalUrl') is not None:
            raise ValueError('Despesa do Senado com link de portal da Câmara')
        safe_money(row['cents'])
        key = (row['memberId'], row['year'], row['month'], row['party'], row['category'], row['inMandate'])
        detail_totals[key] += row['cents']
        detail_counts[key] += 1
    for row in summary:
        safe_money(row['cents'])
        key = (row['memberId'], row['year'], row['month'], row['party'], row['category'], row['inMandate'])
        summary_totals[key] += row['cents']
        summary_counts[key] += row['count']
    # Comparar dicts, inclusive grupos com soma zero.
    if dict(detail_totals) != dict(summary_totals) or dict(detail_counts) != dict(summary_counts):
        raise ValueError('Agregados não reconciliam com detalhes')
    for member in members.values():
        for resource in member.get('otherResources', []):
            safe_money(resource['cents'])
    safe_money(sum(row['cents'] for row in records))

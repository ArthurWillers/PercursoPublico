"""python -m pipeline.collect [--start-year 2008] [--end-year YYYY] [--review-history]."""
import argparse
import gc
import hashlib
import json
import os
import shutil
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from pipeline.http import Client
from pipeline.sources import camara, senado, tse
from pipeline.aggregate.expenses import summarize, summarize_suppliers
from pipeline.aggregate.people import write_people
from pipeline.validate.people import validate_people
from pipeline.validate.integrity import validate, validate_suppliers, validate_election, safe_money


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def publish(destination, members, records, summaries, metadata, year_batches=None, suppliers=None, elections=None, election_batches=None, sources_fn=None, people_fn=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.financial-data-', dir=destination.parent))
    backup = destination.with_name('.data-previous')
    try:
        profiles = []
        for member in sorted(members.values(), key=lambda row: row['id']):
            profiles.append({key: value for key, value in member.items() if key not in ('affiliations', 'otherResources', 'otherResourcesCoverage')})
            write_json(staging / 'members' / (member['id'] + '.json'), member)
        write_json(staging / 'members.json', profiles)
        del profiles
        if year_batches is None:
            year_batches = ((year, [row for row in records if row['year'] == year]) for year in metadata['years'])
        for batch in year_batches:
            if len(batch) == 3:
                year, year_records, supplier_summary = batch
            else:
                year, year_records = batch
                supplier_summary = suppliers[year] if suppliers and year in suppliers else summarize_suppliers(year_records, year)
            grouped = defaultdict(list)
            for row in year_records:
                grouped[row['memberId']].append(row)
            write_json(staging / f'summary-{year}.json', summaries.pop(year, None) or summarize(year_records))
            write_json(staging / f'suppliers-{year}.json', supplier_summary)
            # Um arquivo vazio significa fonte coletada com sucesso, sem registros publicados.
            for member_id in members:
                write_json(staging / 'expenses' / member_id / f'{year}.json',
                           sorted(grouped[member_id], key=lambda row: (row['month'], row['id'])))
            del grouped, year_records, supplier_summary
            gc.collect()
        if elections:
            for election_year, election_data in sorted(elections.items()):
                write_json(staging / f'elections-{election_year}.json', election_data)
        if election_batches is not None:
            for election_year, election_data in election_batches:
                write_json(staging / f'elections-{election_year}.json', election_data)
                del election_data
                gc.collect()
        if people_fn is not None:
            metadata['people'] = people_fn(staging)
        if sources_fn is not None:
            metadata['sources'] = sources_fn()
        write_json(staging / 'index.json', {key: value for key, value in metadata.items() if key != 'sources'})
        metadata['files'] = {str(path.relative_to(staging)): hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in sorted(staging.rglob('*.json'))}
        metadata['profileIds'] = sorted(members)
        write_json(staging / 'manifest.json', metadata)
        verify_output(staging)
        if backup.exists():
            shutil.rmtree(backup)
        if destination.exists():
            os.replace(destination, backup)
        try:
            os.replace(staging, destination)
        except BaseException:
            if backup.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def verify_output(directory):
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest['schemaVersion'] not in ('1.1.0', '1.2.0', '1.3.0'):
        raise ValueError('Schema desconhecido')
    for relative, expected in manifest['files'].items():
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Caminho de manifesto inválido')
        if hashlib.sha256((directory / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Checksum inválido: {relative}')
    members = {row['id']: row for row in json.loads((directory / 'members.json').read_text())}
    if sorted(members) != manifest['profileIds']:
        raise ValueError('Perfis não reconciliam com manifesto')
    for member_id, member in members.items():
        profile = json.loads((directory / 'members' / (member_id + '.json')).read_text())
        if profile['id'] != member_id or any(profile.get(key) != value for key, value in member.items()):
            raise ValueError('Perfil detalhado diverge do cadastro')
        validate([], [], {member_id: profile})
    seen_senate_ids = set()
    historical_cents = 0
    for year in manifest['years']:
        records = []
        for member_id in members:
            details = json.loads((directory / 'expenses' / member_id / f'{year}.json').read_text())
            if any(row['memberId'] != member_id or row['year'] != year for row in details):
                raise ValueError('Arquivo detalhado contém parlamentar ou ano divergente')
            records.extend(details)
        summary = json.loads((directory / f'summary-{year}.json').read_text())
        validate(records, summary, members)
        suppliers_path = directory / f'suppliers-{year}.json'
        if manifest['schemaVersion'] == '1.3.0' or suppliers_path.exists():
            suppliers_summary = json.loads(suppliers_path.read_text())
            validate_suppliers(records, suppliers_summary, members, year)
            del suppliers_summary
        for row in records:
            if row['id'].startswith('senado:'):
                if row['id'] in seen_senate_ids:
                    raise ValueError(f"ID do Senado duplicado entre anos: {row['id']}")
                seen_senate_ids.add(row['id'])
        historical_cents += sum(row['cents'] for row in records)
        for coverage in manifest['coverage']:
            if coverage['year'] == year:
                house_rows = [row for row in records if members[row['memberId']]['chamber'] == coverage['chamber']]
                if coverage['records'] != len(house_rows) or coverage['cents'] != sum(row['cents'] for row in house_rows):
                    raise ValueError('Cobertura não reconcilia com detalhes')
        del records, summary
    for election_year in manifest.get('electionYears', []):
        election_path = directory / f'elections-{election_year}.json'
        if election_path.exists():
            election_data = json.loads(election_path.read_text())
            validate_election(election_data)
            del election_data
    validate_people(directory)
    safe_money(historical_cents)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-year', type=int, default=2008)
    parser.add_argument('--end-year', type=int, default=datetime.now(timezone.utc).year)
    parser.add_argument('--resume', action='store_true', help='Desenvolvimento: reutiliza cache e busca apenas URLs ausentes')
    parser.add_argument('--offline', action='store_true', help='Reprocessa exclusivamente o cache, sem nova coleta')
    parser.add_argument('--review-history', action='store_true', help='Revalida também o histórico antigo antes do prazo anual')
    parser.add_argument('--output', type=Path, default=Path('public/data'))
    args = parser.parse_args()
    if not 2008 <= args.start_year <= args.end_year <= datetime.now(timezone.utc).year:
        parser.error('Intervalo suportado: 2008 até o ano corrente')
    years = list(range(args.start_year, args.end_year + 1))
    client = Client(offline=args.offline, reuse_cache=args.resume, review_history=args.review_history)
    current_deputies = camara.registry(client)
    current_senators = senado.registry(client)
    deputy_ids = set(current_deputies)
    senator_ids = set(current_senators)
    for year in years:
        print(f'Coletando CEAP/CEAPS {year}...', flush=True)
        rows, _url = camara.annual_rows(client, year)
        deputy_ids.update('camara:' + row['ideCadastro'] for row in rows if row['ideCadastro'])
        rows, _url = senado.annual_rows(client, year)
        senator_ids.update('senado:' + str(row['codSenador']) for row in rows)
        del rows
    print(f'Coletando perfis/históricos: {len(deputy_ids)} deputados e {len(senator_ids)} senadores...', flush=True)
    members = camara.profiles(client, deputy_ids, current_deputies)
    print('Históricos da Câmara completos. Coletando Senado e recursos fora da cota...', flush=True)
    members.update(senado.profiles(client, senator_ids, current_senators, years))
    summaries = {}
    coverage = []
    mandate_supplier_keys = set()
    cached_sources = Client(cache=client.cache, offline=True)

    def normalized_years():
        for year in years:
            print(f'Normalizando e validando {year}...', flush=True)
            year_records = []
            for chamber, source in (('deputados', camara), ('senadores', senado)):
                rows, url = source.annual_rows(cached_sources, year)
                unattributed = {'records': 0, 'cents': 0}
                if chamber == 'deputados':
                    normalized, unattributed = camara.normalize(rows, year, members, url)
                else:
                    normalized = senado.normalize(rows, year, members, url)
                year_records.extend(normalized)
                coverage.append({'chamber': chamber, 'year': year, 'status': 'collected',
                                 'ongoing': year == datetime.now(timezone.utc).year,
                                 'sourceUrl': url, 'fetchedAt': client.sources[url]['fetchedAt'],
                                 'records': len(normalized), 'cents': sum(row['cents'] for row in normalized),
                                 'latestMonth': max((row['month'] for row in normalized), default=None),
                                 'unattributed': unattributed})
                del rows, normalized
            summaries[year] = summarize(year_records)
            supplier_summary = summarize_suppliers(year_records, year)
            for s_row in supplier_summary['rows']:
                mandate_supplier_keys.add(s_row['supplierKey'])
            validate(year_records, summaries[year], members)
            validate_suppliers(year_records, supplier_summary, members, year)
            yield year, year_records, supplier_summary
            del year_records, supplier_summary

    for member in members.values():
        if member['mandate']:
            member['mandate']['partial'] = (member['mandate']['start'] < f'{years[0]}-01-01'
                                            or member['mandate']['end'] > datetime.now(timezone.utc).date().isoformat()
                                            or member['mandate']['start'][-2:] != '01')

    election_years = [y for y in tse.ELECTION_YEARS if args.start_year <= y <= args.end_year]
    elections_coverage = []

    def normalized_elections():
        for election_year in election_years:
            print(f'Coletando e validando TSE {election_year}...', flush=True)
            election_data = tse.collect_election_year(client, election_year, mandate_supplier_keys=mandate_supplier_keys)
            validate_election(election_data)
            elections_coverage.append({
                'year': election_year,
                'scope': election_data['scope'],
                'status': election_data['status'],
                'reason': election_data.get('reason'),
                'fetchedAt': election_data.get('fetchedAt'),
                'sourceUrls': election_data['sourceUrls'],
                'candidacies': sum(p['candidacyCount'] for p in election_data['parties']),
                'totalRevenueCents': sum(p['totalRevenueCents'] for p in election_data['parties']),
                'fefcCents': sum(p['fefcCents'] for p in election_data['parties']),
                'partyFundCents': sum(p['partyFundCents'] for p in election_data['parties']),
                'totalExpenseCents': sum(p['totalExpenseCents'] for p in election_data['parties'])
            })
            yield election_year, election_data
            del election_data

    metadata = {'schemaVersion': '1.3.0', 'generatedAt': datetime.now(timezone.utc).isoformat(),
                'collectionMode': 'cached' if args.offline or args.resume else 'live', 'years': years,
                'electionYears': election_years, 'electionsCoverage': elections_coverage,
                'coverage': coverage, 'sources': [],
                'collectionPolicy': {'historicalReviewDays': 365, 'refreshFromYear': datetime.now(timezone.utc).year - 1},
                'methodologyUrl': '/fontes', 'remuneration': {'status': 'not-integrated',
                'reason': 'Não foi validado um vínculo por identificador entre folhas de remuneração e cadastros parlamentares.'}}
    publish(
        args.output,
        members,
        [],
        summaries,
        metadata,
        year_batches=normalized_years(),
        election_batches=normalized_elections(),
        sources_fn=lambda: sorted(client.sources.values(), key=lambda row: row['url']),
        people_fn=lambda directory: write_people(directory, client)
    )
    print(f"Publicado localmente: {len(members)} perfis, {sum(row['records'] for row in coverage)} despesas validadas.", flush=True)


if __name__ == '__main__':
    main()

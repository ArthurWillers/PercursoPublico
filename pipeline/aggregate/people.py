"""Índice de pessoas: ligações por CPF oficial validado, nunca por nome."""
import hashlib
import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError

from pipeline.sources import tse


def valid_cpf(value):
    digits = str(value or '').strip()
    if not re.fullmatch(r'[0-9]{11}', digits) or len(set(digits)) == 1:
        return None
    for length in (9, 10):
        check = (sum(int(digits[index]) * (length + 1 - index) for index in range(length)) * 10) % 11
        if int(digits[length]) != (0 if check == 10 else check):
            return None
    return digits


def person_id(key):
    return 'person:' + hashlib.sha256(key.encode()).hexdigest()[:32]


def assemble_people(members, elections, member_cpfs, candidate_cpfs):
    people = {}

    def get(key):
        identifier = person_id(key)
        return people.setdefault(identifier, {'id': identifier, 'members': [], 'candidacies': [], 'identityBasis': 'official-cpf' if key.startswith('cpf:') else 'source-record'})

    for member in members:
        cpf = valid_cpf(member_cpfs.get(member['id']))
        get(f'cpf:{cpf}' if cpf else member['id'])['members'].append(member)
    for election in elections:
        for candidate in election['candidates']:
            cpf = valid_cpf(candidate_cpfs.get(candidate['id']))
            get(f'cpf:{cpf}' if cpf else candidate['id'])['candidacies'].append(candidate)
    for person in people.values():
        person['members'].sort(key=lambda row: (not row['current'], row['id']))
        person['candidacies'].sort(key=lambda row: (-row['year'], row['id']))
        person['name'] = person['members'][0]['name'] if person['members'] else person['candidacies'][0]['ballotName']
        person['aliases'] = sorted({person['name'], *(row['name'] for row in person['members']),
                                    *(row['name'] for row in person['candidacies']), *(row['ballotName'] for row in person['candidacies'])})
    return sorted(people.values(), key=lambda row: (row['name'].casefold(), row['id']))


def candidate_identifiers(rows, year, published_ids):
    identities, conflicts = {}, set()
    for row in rows:
        sq = tse._first_field(row, 'SQ_CANDIDATO', 'SEQUENCIAL_CANDIDATO', 'Sequencial Candidato')
        identifier = f'tse:{year}:{sq}'
        if identifier not in published_ids or identifier in conflicts:
            continue
        cpf = valid_cpf(tse._first_field(row, 'NR_CPF_CANDIDATO', 'CPF_CANDIDATO', 'CPF candidato', 'CPF do candidato'))
        if not cpf:
            continue
        if identifier in identities and identities[identifier] != cpf:
            conflicts.add(identifier)
            identities.pop(identifier)
            continue
        identities[identifier] = cpf
    return identities, conflicts


def write_people(directory, client):
    members = json.loads((directory / 'members.json').read_text())
    # Durante publish(), o manifesto ainda não foi escrito.
    years = sorted(int(path.stem.split('-')[1]) for path in directory.glob('elections-*.json'))
    elections = []
    candidate_cpfs = {}
    conflicting_ids = set()
    coverage = []
    for year in years:
        election = json.loads((directory / f'elections-{year}.json').read_text())
        elections.append(election)
        if election['status'] != 'collected':
            coverage.append({'year': year, 'status': 'unavailable', 'linkedCandidacies': 0})
            continue
        print(f'Identificando pessoas no cadastro TSE {year}...', flush=True)
        url = election['sourceUrls']['candidates']
        body = client.get(url, cache_days=client.historical_cache_days(year))
        published_ids = {candidate['id'] for candidate in election['candidates']}
        year_cpfs, conflicts = candidate_identifiers(tse._read_csv_from_zip(body, ('consulta_cand',), year=year), year, published_ids)
        candidate_cpfs.update(year_cpfs)
        conflicting_ids.update(conflicts)
        coverage.append({'year': year, 'status': 'collected', 'sourceUrl': url,
                         'fetchedAt': client.sources[url]['fetchedAt'],
                         'linkedCandidacies': sum(identifier in candidate_cpfs for identifier in published_ids),
                         'conflictingCandidacies': len(published_ids & conflicting_ids)})

    def member_identity(member):
        if member['chamber'] != 'deputados':
            return member['id'], None
        try:
            data = client.json(member['sourceUrl'], cache_days=365)['dados']
        except HTTPError as error:
            if error.code != 404:
                raise
            return member['id'], None
        if str(data.get('id')) != member['id'].split(':')[1]:
            raise ValueError('Identificador de cadastro da Câmara divergente')
        return member['id'], valid_cpf(data.get('cpf'))

    print('Conferindo identificadores dos cadastros parlamentares...', flush=True)
    with ThreadPoolExecutor(max_workers=4) as executor:
        member_cpfs = dict(executor.map(member_identity, members))
    people = assemble_people(members, elections, member_cpfs, candidate_cpfs)
    # Remover apenas os links da pasta temporária antes de escrever a nova versão.
    details = directory / 'people'
    if details.exists():
        shutil.rmtree(details)
    details.mkdir()
    index = []
    for person in people:
        (details / f"{person['id']}.json").write_text(json.dumps(person, ensure_ascii=False, separators=(',', ':')))
        index.append({key: person[key] for key in ('id', 'name', 'aliases')} | {
            'memberIds': [row['id'] for row in person['members']],
            'candidateIds': [row['id'] for row in person['candidacies']],
            'current': any(row['current'] for row in person['members']),
            'photoUrl': next((row['photoUrl'] for row in person['members'] if row['photoUrl']), None),
            'years': sorted({row['year'] for row in person['candidacies']}, reverse=True),
            'offices': sorted({row['office'] for row in person['candidacies']}),
            'states': sorted({row['state'] for row in person['members'] + person['candidacies']}),
            'candidacyCount': len(person['candidacies'])
        })
    index.sort(key=lambda person: (not person['current'], person['name'].casefold(), person['id']))
    index_path = directory / 'people.json'
    index_path.unlink(missing_ok=True)
    index_path.write_text(json.dumps({'schemaVersion': '1.0.0', 'coverage': coverage, 'people': index}, ensure_ascii=False, separators=(',', ':')))
    return {'schemaVersion': '1.0.0', 'count': len(index), 'coverage': coverage,
            'method': 'CPF oficial com dígitos verificadores. Registros sem identificador compatível permanecem separados; nomes servem apenas à busca.'}

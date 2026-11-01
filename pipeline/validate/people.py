"""Reconcilia cada vínculo publicado com os arquivos oficiais normalizados."""
import json
import re


def validate_people(directory):
    if not (directory / 'people.json').exists():
        return
    index = json.loads((directory / 'people.json').read_text())
    if index.get('schemaVersion') != '1.0.0':
        raise ValueError('Schema de pessoas desconhecido')
    members = {row['id']: row for row in json.loads((directory / 'members.json').read_text())}
    candidates = {}
    for path in directory.glob('elections-*.json'):
        candidates.update((row['id'], row) for row in json.loads(path.read_text())['candidates'])
    seen_people, seen_members, seen_candidates = set(), set(), set()
    for row in index['people']:
        identifier = row['id']
        if not re.fullmatch(r'person:[a-f0-9]{32}', identifier) or identifier in seen_people:
            raise ValueError('Pessoa duplicada ou identificador inválido')
        seen_people.add(identifier)
        person = json.loads((directory / 'people' / f'{identifier}.json').read_text())
        if person['id'] != identifier or person['name'] != row['name'] or person['aliases'] != row['aliases']:
            raise ValueError('Detalhes de pessoa divergem do índice')
        if person.get('identityBasis') not in ('official-cpf', 'source-record'):
            raise ValueError('Regra de identidade desconhecida')
        if not person['members'] and not person['candidacies']:
            raise ValueError('Pessoa sem registros publicados')
        if person['identityBasis'] == 'source-record' and len(person['members']) + len(person['candidacies']) != 1:
            raise ValueError('Registro sem identidade verificável não pode unir pessoas')
        if row['memberIds'] != [member['id'] for member in person['members']]:
            raise ValueError('Mandatos do índice divergem dos detalhes')
        if row['candidateIds'] != [candidate['id'] for candidate in person['candidacies']]:
            raise ValueError('Identificadores eleitorais do índice divergem dos detalhes')
        if row['candidacyCount'] != len(person['candidacies']) or row['years'] != sorted({candidate['year'] for candidate in person['candidacies']}, reverse=True):
            raise ValueError('Cobertura eleitoral da pessoa divergente')
        expected_aliases = {*(member['name'] for member in person['members']),
                            *(candidate['name'] for candidate in person['candidacies']), *(candidate['ballotName'] for candidate in person['candidacies'])}
        if set(person['aliases']) != expected_aliases or person['name'] not in expected_aliases:
            raise ValueError('Aliases não correspondem aos nomes das fontes')
        expected_photo = next((member['photoUrl'] for member in person['members'] if member['photoUrl']), None)
        if row['photoUrl'] != expected_photo or row['current'] != any(member['current'] for member in person['members']):
            raise ValueError('Foto ou situação parlamentar diverge da origem')
        if row['offices'] != sorted({candidate['office'] for candidate in person['candidacies']}) or row['states'] != sorted({record['state'] for record in person['members'] + person['candidacies']}):
            raise ValueError('Filtros de cargo ou UF não reconciliam com os detalhes')
        for member in person['members']:
            if member['id'] in seen_members or members.get(member['id']) != member:
                raise ValueError('Vínculo parlamentar duplicado ou divergente')
            seen_members.add(member['id'])
        for candidate in person['candidacies']:
            if candidate['id'] in seen_candidates or candidates.get(candidate['id']) != candidate:
                raise ValueError('Candidatura duplicada ou divergente na pessoa')
            seen_candidates.add(candidate['id'])
    if seen_members != set(members) or seen_candidates != set(candidates):
        raise ValueError('Índice de pessoas não reconcilia com os registros publicados')

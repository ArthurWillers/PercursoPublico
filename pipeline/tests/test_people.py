import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from pipeline.aggregate.people import write_people
from pipeline.validate.people import validate_people
from pipeline.sources.tse import normalize_election
from pipeline.aggregate.people import assemble_people, valid_cpf, candidate_identifiers


class PeopleTests(unittest.TestCase):
    def member(self, identifier='camara:1', name='Nome igual'):
        return {'id': identifier, 'name': name, 'current': True, 'photoUrl': None}

    def candidate(self, year, sq, name='Nome igual'):
        return {'id': f'tse:{year}:{sq}', 'year': year, 'name': name, 'ballotName': name, 'totalExpenseCents': -100}

    def test_joins_official_identifiers_across_years_and_different_names(self):
        a, b = self.candidate(2022, '1', 'Nome civil antigo'), self.candidate(2026, '2', 'Nome de urna novo')
        people = assemble_people([self.member()], [{'candidates': [a, b]}], {'camara:1': '11144477735'}, {a['id']: '11144477735', b['id']: '11144477735'})
        self.assertEqual(len(people), 1)
        self.assertEqual([row['year'] for row in people[0]['candidacies']], [2026, 2022])
        self.assertEqual(people[0]['candidacies'][0]['totalExpenseCents'], -100)
        self.assertIn('Nome civil antigo', people[0]['aliases'])
        self.assertNotIn('11144477735', str(people))

    def test_homonyms_and_invalid_identifiers_never_merge(self):
        a, b = self.candidate(2022, '1'), self.candidate(2026, '2')
        people = assemble_people([self.member()], [{'candidates': [a, b]}], {'camara:1': '11144477735'}, {a['id']: '52998224725', b['id']: '00000000000'})
        self.assertEqual(len(people), 3)
        self.assertEqual(sum(person['identityBasis'] == 'source-record' for person in people), 1)
        self.assertIsNone(valid_cpf('***444777**'))
        self.assertIsNone(valid_cpf('11144477734'))

    def test_identity_is_stable_if_names_change(self):
        member = self.member()
        before = assemble_people([member], [], {'camara:1': '11144477735'}, {})
        after = assemble_people([{**member, 'name': 'Outro nome'}], [], {'camara:1': '11144477735'}, {})
        self.assertEqual(before[0]['id'], after[0]['id'])

    def test_conflicting_historical_identifier_is_not_used_for_joining(self):
        rows = [{'SQ_CANDIDATO': '1', 'NR_CPF_CANDIDATO': '11144477735'},
                {'SQ_CANDIDATO': '1', 'NR_CPF_CANDIDATO': '52998224725'},
                {'SQ_CANDIDATO': '1', 'NR_CPF_CANDIDATO': '11144477735'},
                {'SQ_CANDIDATO': '2', 'NR_CPF_CANDIDATO': '11144477735'}]
        identifiers, conflicts = candidate_identifiers(rows, 2008, {'tse:2008:1', 'tse:2008:2'})
        self.assertEqual(identifiers, {'tse:2008:2': '11144477735'})
        self.assertEqual(conflicts, {'tse:2008:1'})

    def test_person_expenses_must_equal_original_candidacy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'members.json').write_text('[]')
            urls = {'candidates': 'https://example.org/c', 'accounts': 'https://example.org/a'}
            election = normalize_election([{'SQ_CANDIDATO': '1', 'CD_CARGO': '6', 'NM_CANDIDATO': 'Pessoa de teste', 'SG_UF': 'SP'}], [], [], 2026, urls)
            (root / 'elections-2026.json').write_text(json.dumps(election))
            client = Mock(sources={urls['candidates']: {'fetchedAt': '2026-11-01T12:00:00+00:00'}})
            client.get.return_value = b'fixture'
            client.historical_cache_days.return_value = 0
            with patch('pipeline.aggregate.people.tse._read_csv_from_zip', return_value=iter([{'SQ_CANDIDATO': '1', 'NR_CPF_CANDIDATO': '11144477735'}])):
                write_people(root, client)
            validate_people(root)
            detail_path = next((root / 'people').glob('*.json'))
            detail = json.loads(detail_path.read_text())
            detail['candidacies'][0]['totalExpenseCents'] += 1
            detail_path.write_text(json.dumps(detail))
            with self.assertRaisesRegex(ValueError, 'Candidatura duplicada ou divergente'):
                validate_people(root)

"""Cargos executivos devem reconciliar sem contaminar as contas do mandato."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from pipeline.http import Client
from pipeline.sources.tse import collect_election_year

from pipeline.sources.tse import normalize_election, _iter_filtered_csv_lines
from pipeline.validate.integrity import validate_election


class ExecutiveElectionTests(unittest.TestCase):
    def test_offices_adjustments_and_rounds_reconcile(self):
        candidates = [
            {'SQ_CANDIDATO': '101', 'CD_CARGO': '1', 'NM_CANDIDATO': 'Presidência teste', 'SG_UF': 'BR', 'SG_PARTIDO': 'A', 'DS_SIT_TOT_TURNO': '2º TURNO'},
            {'SQ_CANDIDATO': '101', 'CD_CARGO': '1', 'NM_CANDIDATO': 'Presidência teste', 'SG_UF': 'BR', 'SG_PARTIDO': 'A', 'DS_SIT_TOT_TURNO': 'ELEITO'},
            {'SQ_CANDIDATO': '102', 'CD_CARGO': '3', 'NM_CANDIDATO': 'Governo teste', 'SG_UF': 'SP', 'SG_PARTIDO': 'A'},
            {'SQ_CANDIDATO': '103', 'CD_CARGO': '2', 'NM_CANDIDATO': 'Vice fora do escopo'}
        ]
        revenues = [
            {'SQ_CANDIDATO': '101', 'CD_CARGO': '1', 'VR_RECEITA': '100,01', 'DS_FONTE_RECEITA': 'FEFC'},
            {'SQ_CANDIDATO': '101', 'CD_CARGO': '1', 'VR_RECEITA': '-0,01', 'DS_FONTE_RECEITA': 'FEFC'},
            {'SQ_CANDIDATO': '102', 'CD_CARGO': '3', 'VR_RECEITA': '50,00', 'DS_FONTE_RECEITA': 'Fundo Partidário'}
        ]
        # Duas ocorrências iguais e um ajuste são três registros, sem deduplicação por valor.
        expenses = [
            {'SQ_CANDIDATO': '101', 'CD_CARGO': '1', 'VR_DESPESA_CONTRATADA': '10,00'},
            {'SQ_CANDIDATO': '101', 'CD_CARGO': '1', 'VR_DESPESA_CONTRATADA': '10,00'},
            {'SQ_CANDIDATO': '101', 'CD_CARGO': '1', 'VR_DESPESA_CONTRATADA': '-1,00'},
            {'SQ_CANDIDATO': '102', 'CD_CARGO': '3', 'VR_DESPESA_CONTRATADA': '5,00'}
        ]
        result = normalize_election(candidates, revenues, expenses, 2026, {'candidates': 'https://example.org/c', 'accounts': 'https://example.org/a'})
        validate_election(result)
        by_id = {candidate['sqCandidato']: candidate for candidate in result['candidates']}
        self.assertEqual(set(by_id), {'101', '102'})
        self.assertTrue(by_id['101']['elected'])
        self.assertEqual(by_id['101']['fefcCents'], 10000)
        self.assertEqual(by_id['101']['totalExpenseCents'], 1900)
        self.assertEqual(by_id['101']['expenseCount'], 3)
        self.assertEqual(by_id['102']['partyFundCents'], 5000)
        self.assertEqual(sum(row['totalExpenseCents'] for row in result['parties']), 2400)
        self.assertIn('presidente', result['collectedOffices'])
        self.assertIn('governador', result['collectedOffices'])

    def test_stream_filters_by_election_scope(self):
        lines = ['SQ_CANDIDATO;CD_CARGO;NM_CANDIDATO\n', '1;1;Presidente\n', '2;3;Governador\n', '3;11;Prefeito\n', '4;7;Estadual\n']
        general = list(_iter_filtered_csv_lines(lines, 2026))
        self.assertEqual([row['_office'] for row in general], ['presidente', 'governador'])
        municipal = list(_iter_filtered_csv_lines(lines, 2024))
        self.assertEqual([row['_office'] for row in municipal], ['prefeito'])

    def test_source_failure_is_not_published_as_missing_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            client = Client(cache=Path(temporary))
            with patch('pipeline.sources.tse._http_head_meta', side_effect=HTTPError('https://example.org', 503, 'Unavailable', None, None)):
                with self.assertRaises(HTTPError):
                    collect_election_year(client, 2026)
            with patch('pipeline.sources.tse._http_head_meta', side_effect=HTTPError('https://example.org', 404, 'Not Found', None, None)):
                result = collect_election_year(client, 2026)
                self.assertEqual(result['status'], 'unavailable')
                validate_election(result)

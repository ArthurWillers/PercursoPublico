import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.collect import publish, verify_output
from pipeline.http import Client
from pipeline.refresh_elections import refresh_elections
from pipeline.sources.tse import normalize_election, unavailable_election


class RefreshElectionTests(unittest.TestCase):
    def snapshot(self, root):
        destination = root / 'data'
        election = normalize_election([], [], [], 2026, {'candidates': 'https://example.org/c', 'accounts': 'https://example.org/a'})
        metadata = {'schemaVersion': '1.3.0', 'years': [2026], 'coverage': [], 'sources': [],
                    'electionYears': [2026], 'electionsCoverage': [{'year': 2026, 'status': 'collected'}]}
        publish(destination, {}, [], {2026: []}, metadata, elections={2026: election})
        return destination, election

    def test_replaces_election_and_reconciles_manifest_without_changing_mandate_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination, _ = self.snapshot(root)
            before = (destination / 'suppliers-2026.json').read_bytes()
            election = normalize_election([{'SQ_CANDIDATO': '42', 'CD_CARGO': '1', 'SG_UF': 'BR'}], [], [], 2026,
                                          {'candidates': 'https://example.org/c', 'accounts': 'https://example.org/a'})
            with patch('pipeline.refresh_elections.tse.collect_election_year', return_value=election):
                refresh_elections(destination, Client(cache=root / 'cache', offline=True), [2026])
            manifest = verify_output(destination)
            self.assertEqual(manifest['electionsCoverage'][0]['candidacies'], 1)
            self.assertEqual((destination / 'suppliers-2026.json').read_bytes(), before)
            self.assertEqual(json.loads((destination / 'elections-2026.json').read_text())['candidates'][0]['office'], 'presidente')
            self.assertFalse(destination.with_name('.data-previous').exists())

    def test_failed_validation_and_missing_source_preserve_previous_bytes(self):
        for failure in ('validation', 'missing'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                destination, election = self.snapshot(root)
                before = {path.name: path.read_bytes() for path in destination.glob('*.json')}
                result = unavailable_election(2026, 'Indisponível') if failure == 'missing' else election
                with patch('pipeline.refresh_elections.tse.collect_election_year', return_value=result):
                    with patch('pipeline.refresh_elections.verify_output', side_effect=ValueError('Falha de integridade')):
                        with self.assertRaises(ValueError):
                            refresh_elections(destination, Client(cache=root / 'cache', offline=True), [2026])
                self.assertEqual({path.name: path.read_bytes() for path in destination.glob('*.json')}, before)
                self.assertFalse(list(root.glob('.financial-data-*')))

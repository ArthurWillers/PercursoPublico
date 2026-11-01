"""Fotos oficiais e situação da candidatura do TSE, sem chamadas à rede."""
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.aggregate.people import person_photo_path
from pipeline.sources import tse, tse_photos
from pipeline.validate.integrity import validate_election

JPEG = b'\xff\xd8\xff\xe0'


def candidate(sq, office='presidente', state='BR', year=2018):
    return {'id': f'tse:{year}:{sq}', 'sqCandidato': sq, 'year': year, 'office': office, 'state': state}


def build_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('leiame.pdf', b'%PDF')
        archive.writestr('FBR280000625869_div.jpg', JPEG + b'A' * 80, compress_type=zipfile.ZIP_STORED)
        archive.writestr('FBR280000625870_div.jpeg', JPEG + b'B' * 400, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr('FBR280000625871_div.jpg', JPEG + b'C' * 50, compress_type=zipfile.ZIP_STORED)
        archive.writestr('FSP250000000001_div.jpg', JPEG + b'D' * 50, compress_type=zipfile.ZIP_STORED)
    raw = buffer.getvalue()
    # Altera o conteúdo sem mudar o CRC declarado: a imagem deve ser descartada.
    return raw.replace(JPEG + b'C' * 50, JPEG + b'X' * 50)


class TsePhotoTests(unittest.TestCase):
    def setUp(self):
        self.data = build_zip()
        self.requests = 0

        def range_get(_url, start, end, timeout=90):
            self.requests += 1
            return self.data[start:end + 1]

        meta = {'size': len(self.data), 'fetchedAt': '2026-11-01T00:00:00+00:00'}
        self.patches = [patch.object(tse, '_http_range_get', range_get), patch.object(tse, '_http_head_meta', lambda *_a, **_k: meta)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_only_verified_executive_photos_are_published(self):
        election = {'year': 2018, 'status': 'collected', 'candidates': [
            candidate('280000625869'), candidate('280000625870'), candidate('280000625871'),
            candidate('280000625999'), candidate('280000625872', office='deputado_federal')]}
        with tempfile.TemporaryDirectory() as directory:
            client = SimpleNamespace(cache=Path(directory) / 'cache', offline=False)
            staging = Path(directory) / 'staging'
            published = tse_photos.stage_photos(client, election, staging)
            self.assertEqual(sorted(published), ['photos/2018/280000625869.jpg', 'photos/2018/280000625870.jpg'])
            self.assertEqual((staging / published[0]).read_bytes(), JPEG + b'A' * 80)
            self.assertEqual((staging / published[1]).read_bytes(), JPEG + b'B' * 400)
            with_photo = {row['sqCandidato'] for row in election['candidates'] if 'photoPath' in row}
            self.assertEqual(with_photo, {'280000625869', '280000625870'})
            self.assertFalse((staging / 'photos/2018/280000625871.jpg').exists())

    def test_cached_photos_do_not_require_the_network(self):
        election = {'year': 2018, 'status': 'collected', 'candidates': [candidate('280000625869')]}
        with tempfile.TemporaryDirectory() as directory:
            client = SimpleNamespace(cache=Path(directory) / 'cache', offline=False)
            tse_photos.stage_photos(client, election, Path(directory) / 'first')
            before = self.requests
            offline = SimpleNamespace(cache=client.cache, offline=True)
            repeated = {'year': 2018, 'status': 'collected', 'candidates': [candidate('280000625869')]}
            self.assertEqual(tse_photos.stage_photos(offline, repeated, Path(directory) / 'second'), ['photos/2018/280000625869.jpg'])
            self.assertEqual(self.requests, before)

    def test_unavailable_elections_and_missing_packages_do_not_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            client = SimpleNamespace(cache=Path(directory) / 'cache', offline=False)
            self.assertEqual(tse_photos.stage_photos(client, {'year': 2018, 'status': 'unavailable', 'candidates': []}, Path(directory)), [])
            with patch.object(tse, '_fetch_remote_zip_directory', side_effect=ValueError('ausente')):
                election = {'year': 2018, 'status': 'collected', 'candidates': [candidate('280000625869')]}
                self.assertEqual(tse_photos.stage_photos(client, election, Path(directory) / 'staging'), [])
                self.assertNotIn('photoPath', election['candidates'][0])


class CandidacyStatusTests(unittest.TestCase):
    def test_inapt_candidacy_keeps_source_status_instead_of_looking_like_a_normal_result(self):
        rows = [{'SQ_CANDIDATO': '280000625869', 'DS_CARGO': 'PRESIDENTE', 'NM_CANDIDATO': 'LUIZ INÁCIO LULA DA SILVA',
                 'NM_URNA_CANDIDATO': 'LULA', 'NR_CANDIDATO': '13', 'SG_PARTIDO': 'PT', 'SG_UF': 'BR',
                 'DS_SITUACAO_CANDIDATURA': 'INAPTO', 'DS_SIT_TOT_TURNO': '#NULO#'},
                {'SQ_CANDIDATO': '280000625870', 'DS_CARGO': 'PRESIDENTE', 'NM_CANDIDATO': 'OUTRA PESSOA',
                 'NM_URNA_CANDIDATO': 'OUTRA', 'NR_CANDIDATO': '45', 'SG_PARTIDO': 'XX', 'SG_UF': 'BR',
                 'DS_SITUACAO_CANDIDATURA': 'APTO', 'DS_DETALHE_SITUACAO_CAND': 'DEFERIDO', 'DS_SIT_TOT_TURNO': 'NÃO ELEITO'}]
        election = tse.normalize_election(rows, [], [], 2018, {'candidates': 'https://cdn.tse.jus.br/c.zip', 'accounts': 'https://cdn.tse.jus.br/a.zip'})
        validate_election(election)
        inapt, apt = election['candidates'][0], election['candidates'][1]
        by_id = {row['sqCandidato']: row for row in election['candidates']}
        inapt, apt = by_id['280000625869'], by_id['280000625870']
        self.assertEqual((inapt['candidacyStatus'], inapt['result'], inapt['elected']), ('Inapto', 'Sem totalização', False))
        self.assertEqual((apt['candidacyStatus'], apt['candidacyDetail']), ('Apto', 'Deferido'))

    def test_candidacy_created_only_from_accounts_has_no_status(self):
        revenue = [{'SQ_CANDIDATO': '280000625869', '_office': 'presidente', 'VR_RECEITA': '10,00', 'DS_ORIGEM_RECEITA': 'Recursos próprios'}]
        election = tse.normalize_election([], revenue, [], 2018, {'candidates': 'https://cdn.tse.jus.br/c.zip', 'accounts': 'https://cdn.tse.jus.br/a.zip'})
        self.assertIsNone(election['candidates'][0]['candidacyStatus'])

    def test_photo_path_must_match_the_candidacy(self):
        election = tse.normalize_election([{'SQ_CANDIDATO': '280000625869', 'DS_CARGO': 'PRESIDENTE', 'NM_CANDIDATO': 'A', 'NM_URNA_CANDIDATO': 'A',
                                            'NR_CANDIDATO': '1', 'SG_PARTIDO': 'P', 'SG_UF': 'BR', 'DS_SIT_TOT_TURNO': 'ELEITO'}], [], [], 2018,
                                          {'candidates': 'https://cdn.tse.jus.br/c.zip', 'accounts': 'https://cdn.tse.jus.br/a.zip'})
        election['candidates'][0]['photoPath'] = 'photos/2018/280000625869.jpg'
        validate_election(election)
        election['candidates'][0]['photoPath'] = 'photos/2018/999.jpg'
        with self.assertRaisesRegex(ValueError, 'foto'):
            validate_election(election)

    def test_person_uses_most_recent_official_photo(self):
        person = {'candidacies': [{'year': 2022, 'photoPath': None}, {'year': 2018, 'photoPath': 'photos/2018/1.jpg'}, {'year': 2014, 'photoPath': 'photos/2014/2.jpg'}]}
        self.assertEqual(person_photo_path(person), 'photos/2018/1.jpg')
        self.assertIsNone(person_photo_path({'candidacies': [{'year': 2022}]}))


if __name__ == '__main__':
    unittest.main()


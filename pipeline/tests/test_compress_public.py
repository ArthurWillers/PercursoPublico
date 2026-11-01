import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.compress_public import compress_public_data


class CompressPublicTests(unittest.TestCase):
    def test_compresses_directly_from_source_without_copying_or_changing_raw_data(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / 'raw'
            source.mkdir()
            content = b'[{"memberId":"camara:123","cents":-100}]'
            (source / 'summary-2008.json').write_bytes(content)
            original_manifest = json.dumps({'files': {'summary-2008.json': hashlib.sha256(content).hexdigest()}})
            (source / 'manifest.json').write_text(original_manifest)
            output = root / 'site' / 'data'
            compress_public_data(output, source_directory=source)
            self.assertEqual((source / 'summary-2008.json').read_bytes(), content)
            self.assertEqual((source / 'manifest.json').read_text(), original_manifest)
            self.assertFalse((output / 'summary-2008.json').exists())
            self.assertEqual(gzip.decompress((output / 'summary-2008.json.gz').read_bytes()), content)
            (source / 'summary-2008.json').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'mudou antes da compactação'):
                compress_public_data(output, source_directory=source)

    def test_compresses_large_json_and_updates_published_checksums(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            site = Path(temporary_directory)
            data = site / 'data'
            (data / 'members').mkdir(parents=True)
            (data / 'people').mkdir()
            (data / 'expenses' / 'camara:123').mkdir(parents=True)
            source_files = {
                'people.json': b'{"schemaVersion":"1.0.0","people":[]}',
                'people/person-1.json': b'{"id":"person-1"}',
                'summary-2026.json': b'[{"memberId":"camara:123","cents":100}]',
                'members/camara:123.json': b'{"id":"camara:123"}',
                'expenses/camara:123/2026.json': b'[{"id":"doc:1","cents":100}]',
                'members.json': b'[{"id":"camara:123"}]'
            }
            checksums = {}
            for relative_path, content in source_files.items():
                path = data / relative_path
                path.write_bytes(content)
                checksums[relative_path] = hashlib.sha256(content).hexdigest()
            (data / 'manifest.json').write_text(json.dumps({'files': checksums}), encoding='utf-8')

            compress_public_data(data)

            manifest = json.loads((data / 'manifest.json').read_text(encoding='utf-8'))
            for relative_path, content in source_files.items():
                path = data / relative_path
                if relative_path == 'members.json':
                    self.assertTrue(path.exists())
                    continue
                compressed_path = Path(str(path) + '.gz')
                compressed_bytes = compressed_path.read_bytes()
                self.assertFalse(path.exists())
                self.assertEqual(gzip.decompress(compressed_bytes), content)
                self.assertEqual(manifest['files'][relative_path + '.gz'], hashlib.sha256(compressed_bytes).hexdigest())
                self.assertNotIn(relative_path, manifest['files'])


if __name__ == '__main__':
    unittest.main()

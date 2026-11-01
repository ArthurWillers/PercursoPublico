"""Restaura e valida o snapshot compactado atualmente publicado no GitHub Pages."""
import argparse
import gzip
import hashlib
from http.client import IncompleteRead, RemoteDisconnected
import json
import os
import re
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from pipeline.collect import verify_output


def _read_url(url, timeout):
    request = Request(url, headers={'User-Agent': 'PercursoPublico/1.0'})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
        except (IncompleteRead, RemoteDisconnected, URLError, TimeoutError):
            if attempt == 3:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError(f'Falha ao baixar arquivo publicado: {url}')


def _relative_json_path(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Caminho inválido no manifesto publicado')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not value.endswith(('.json', '.json.gz')):
        raise ValueError('Caminho inválido no manifesto publicado')
    return path


def restore_public_snapshot(site_url, destination=Path('public/data')):
    """Baixa arquivos publicados, verifica checksums e descompacta em modo transacional."""
    base = site_url.rstrip('/') + '/'
    manifest_url = urljoin(base, 'data/manifest.json')
    manifest = json.loads(_read_url(manifest_url, timeout=90))
    if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), dict) or not manifest['files']:
        raise ValueError('Manifesto publicado inválido ou sem arquivos')

    entries = []
    destinations = set()
    for relative, expected in manifest['files'].items():
        path = _relative_json_path(relative)
        if not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected):
            raise ValueError(f'Checksum inválido no manifesto: {relative}')
        is_compressed = relative.endswith('.json.gz')
        output_path = PurePosixPath(str(path)[:-3]) if is_compressed else path
        if output_path in destinations or output_path == PurePosixPath('manifest.json'):
            raise ValueError(f'Caminho duplicado ou reservado no manifesto: {relative}')
        destinations.add(output_path)
        encoded = '/'.join(quote(part, safe=':@') for part in path.parts)
        entries.append((relative, output_path, expected, is_compressed, urljoin(base, 'data/' + encoded)))

    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.public-snapshot-', dir=parent))
    backup = destination.with_name('.data-restore-previous')

    def download(entry):
        relative, output_path, expected, is_compressed, url = entry
        body = _read_url(url, timeout=120)
        if hashlib.sha256(body).hexdigest() != expected:
            raise ValueError(f'Checksum publicado divergente: {relative}')
        content = gzip.decompress(body) if is_compressed else body
        raw_relative = str(output_path)
        return raw_relative, content, hashlib.sha256(content).hexdigest()

    try:
        raw_checksums = {}
        with ThreadPoolExecutor(max_workers=8) as executor:
            for relative, content, checksum in executor.map(download, entries):
                path = staging / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                raw_checksums[relative] = checksum
        manifest['files'] = raw_checksums
        (staging / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
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

    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site-url', required=True, help='URL base fornecida pelo GitHub Pages')
    parser.add_argument('--output', type=Path, default=Path('public/data'))
    args = parser.parse_args()
    manifest = restore_public_snapshot(args.site_url, args.output)
    print(f"Snapshot publicado restaurado e validado: schema {manifest['schemaVersion']}, {len(manifest['profileIds'])} perfis.", flush=True)


if __name__ == '__main__':
    main()

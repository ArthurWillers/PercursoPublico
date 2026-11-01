"""Compacta os arquivos volumosos publicados no site estático."""
import gzip
import hashlib
import json
from pathlib import Path

DATA_DIRECTORY = Path('.output/public/data')
MAXIMUM_SITE_BYTES = 1_000_000_000


def compress_public_data(directory=DATA_DIRECTORY, source_directory=None):
    source_directory = source_directory or directory
    directory.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((source_directory / 'manifest.json').read_text(encoding='utf-8'))
    checksums = manifest['files']
    compressed_count = 0
    for relative, expected in list(checksums.items()):
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Caminho de manifesto inválido')
        original = (source_directory / relative).read_bytes()
        if hashlib.sha256(original).hexdigest() != expected:
            raise ValueError(f'Arquivo mudou antes da compactação: {relative}')
        compress = path.parts[0] in ('members', 'expenses', 'people') or path.name == 'people.json' or path.name.startswith(('summary-', 'suppliers-', 'elections-'))
        target = directory / (relative + '.gz' if compress else relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = gzip.compress(original, compresslevel=9, mtime=0) if compress else original
        target.write_bytes(content)
        if compress:
            if (directory / relative).exists():
                (directory / relative).unlink()
            checksums[relative + '.gz'] = hashlib.sha256(content).hexdigest()
            del checksums[relative]
            compressed_count += 1

    (directory / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    site_directory = directory.parent
    total_bytes = sum(path.stat().st_size for path in site_directory.rglob('*') if path.is_file())
    if total_bytes >= MAXIMUM_SITE_BYTES:
        raise ValueError(f'Site compactado excede o limite de publicação de 1 GB: {total_bytes:,} bytes')
    print(f'Site compacto pronto: {total_bytes:,} bytes; {compressed_count:,} arquivos JSON compactados.')


if __name__ == '__main__':
    compress_public_data(source_directory=Path('public/data'))

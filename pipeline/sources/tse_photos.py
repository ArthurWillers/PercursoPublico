"""Fotos oficiais de candidaturas do TSE (dados abertos) para Presidente e Governador.

Os pacotes `foto_cand{ano}_{UF}_div.zip` têm centenas de MB. Apenas as imagens necessárias são lidas por
HTTP Range e cada uma é conferida pelo CRC32 do próprio ZIP. A foto é opcional: falha ou ausência nunca
interrompem a coleta, e a interface mantém iniciais como alternativa.
"""
import os
import re
import shutil
import struct
import zlib
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError

from pipeline.sources import tse

OPEN_DATA = 'https://cdn.tse.jus.br/estatistica/sead'
PHOTO_OFFICES = frozenset({'presidente', 'governador'})
PHOTO_NAME = re.compile(r'^F[A-Z]{2}(\d+)(?:_div)?\.jpe?g$', re.IGNORECASE)
MAX_PHOTO_BYTES = 400_000
JPEG_MAGIC = b'\xff\xd8\xff'


def photos_url(year, state):
    return f'{OPEN_DATA}/eleicoes/eleicoes{year}/fotos/foto_cand{year}_{state}_div.zip'


def photo_path(year, sq):
    return f'photos/{year}/{sq}.jpg'


def _photo_entries(url):
    meta = tse._http_head_meta(url)
    entries = tse._fetch_remote_zip_directory(url, meta['size'])
    found = {}
    for name, entry in entries.items():
        match = PHOTO_NAME.match(name.rsplit('/', 1)[-1])
        if match and entry['uncompSize'] <= MAX_PHOTO_BYTES:
            found[match.group(1)] = entry
    return found


def _read_entry(url, entry):
    """Lê uma entrada ZIP armazenada ou comprimida e confere o CRC32 declarado no diretório central."""
    offset, size = entry['localOffset'], entry['compSize']
    block = tse._http_range_get(url, offset, offset + 30 + 1024 + size - 1)
    if block[:4] != b'PK\x03\x04':
        raise ValueError(f'Cabeçalho local ZIP inválido em {url}')
    name_length, extra_length = struct.unpack('<HH', block[26:30])
    start = 30 + name_length + extra_length
    if len(block) < start + size:
        block = tse._http_range_get(url, offset, offset + start + size - 1)
    data = block[start:start + size]
    if len(data) != size:
        raise ValueError(f'Imagem incompleta em {url}')
    if entry['method'] == 8:
        data = zlib.decompress(data, -zlib.MAX_WBITS)
    elif entry['method'] != 0:
        raise ValueError('Método de compressão ZIP não suportado para imagem')
    if zlib.crc32(data) & 0xFFFFFFFF != entry['crc32'] or not data.startswith(JPEG_MAGIC):
        raise ValueError('Imagem corrompida ou fora do formato esperado')
    return data


def _cache_file(client, year, sq):
    return client.cache / 'photos' / str(year) / f'{sq}.jpg'


def _fetch_state(client, year, state, candidates):
    cached = {sq: _cache_file(client, year, sq) for sq in candidates}
    missing = [sq for sq, path in cached.items() if not path.exists()]
    if missing and not client.offline:
        url = photos_url(year, state)
        try:
            entries = _photo_entries(url)
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
            print(f'Fotos TSE {year}/{state} indisponíveis ({exc.__class__.__name__}).', flush=True)
            entries = {}

        def download(sq):
            entry = entries.get(sq)
            if entry is None:
                return
            try:
                data = _read_entry(url, entry)
            except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError, zlib.error):
                return
            target = cached[sq]
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix('.tmp')
            temporary.write_bytes(data)
            os.replace(temporary, target)

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(download, missing))
    return {sq: path for sq, path in cached.items() if path.exists()}


def stage_photos(client, election, staging):
    """Copia para `staging/photos/{ano}/{sq}.jpg` as fotos disponíveis e registra `photoPath` nas candidaturas.

    Retorna os caminhos relativos publicados. Candidaturas sem foto oficial ficam sem `photoPath`.
    """
    if election.get('status') != 'collected':
        return []
    wanted = {}
    for candidate in election.get('candidates', []):
        if candidate['office'] in PHOTO_OFFICES:
            wanted.setdefault(candidate['state'], {})[candidate['sqCandidato']] = candidate
    published = []
    for state, candidates in sorted(wanted.items()):
        for sq, source in _fetch_state(client, election['year'], state, candidates).items():
            relative = photo_path(election['year'], sq)
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.unlink(missing_ok=True)
            shutil.copyfile(source, target)
            candidates[sq]['photoPath'] = relative
            published.append(relative)
    return published


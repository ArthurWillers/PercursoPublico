"""Atualiza pleitos selecionados sem reprocessar as despesas das Casas."""
import argparse
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pipeline.collect import verify_output, write_json
from pipeline.http import Client
from pipeline.sources import tse, tse_photos
from pipeline.validate.integrity import validate_election


def refresh_elections(destination, client, years, include_people=False):
    manifest = json.loads((destination / 'manifest.json').read_text())
    if any(year not in manifest.get('electionYears', []) for year in years):
        raise ValueError('Atualização restrita aos pleitos do manifesto existente')
    supplier_keys = set()
    for year in manifest['years']:
        path = destination / f'suppliers-{year}.json'
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['files'][path.name]:
            raise ValueError(f'Checksum inválido: {path.name}')
        suppliers = json.loads(path.read_text())
        supplier_keys.update(row['supplierKey'] for row in suppliers['rows'])
    staging = Path(tempfile.mkdtemp(prefix='.financial-data-', dir=destination.parent))
    backup = destination.with_name('.data-previous')
    try:
        # Arquivos imutáveis são compartilhados. Cada JSON alterado é desvinculado antes de escrever.
        shutil.copytree(destination, staging, copy_function=os.link, dirs_exist_ok=True)
        coverage = {row['year']: row for row in manifest.get('electionsCoverage', [])}
        for year in years:
            print(f'Atualizando e validando TSE {year}...', flush=True)
            election = tse.collect_election_year(client, year, mandate_supplier_keys=supplier_keys)
            validate_election(election)
            if election['status'] != 'collected' and coverage.get(year, {}).get('status') == 'collected':
                raise ValueError(f'Coleta TSE {year} indisponível; preservar versão válida anterior')
            path = staging / f'elections-{year}.json'
            path.unlink(missing_ok=True)
            for relative in tse_photos.stage_photos(client, election, staging):
                manifest['files'][relative] = hashlib.sha256((staging / relative).read_bytes()).hexdigest()
            write_json(path, election)
            coverage[year] = {
                key: election.get(key) for key in ('year', 'scope', 'status', 'reason', 'fetchedAt', 'sourceUrls')
            }
            coverage[year]['candidacies'] = sum(row['candidacyCount'] for row in election['parties'])
            for field in ('totalRevenueCents', 'fefcCents', 'partyFundCents', 'totalExpenseCents'):
                coverage[year][field] = sum(row[field] for row in election['parties'])
            manifest['files'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        if include_people or (staging / 'people.json').exists():
            from pipeline.aggregate.people import write_people
            manifest['people'] = write_people(staging, client)
            manifest['files'] = {key: value for key, value in manifest['files'].items() if key != 'people.json' and not key.startswith('people/')}
            for path in [staging / 'people.json', *(staging / 'people').glob('*.json')]:
                manifest['files'][path.relative_to(staging).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest['electionsCoverage'] = [coverage[year] for year in sorted(coverage)]
        manifest['generatedAt'] = datetime.now(timezone.utc).isoformat()
        manifest['collectionMode'] = 'cached' if client.offline or client.reuse_cache else 'live'
        sources = {row['url']: row for row in manifest['sources']}
        sources.update(client.sources)
        manifest['sources'] = sorted(sources.values(), key=lambda row: row['url'])
        index = {key: value for key, value in manifest.items() if key not in ('sources', 'files', 'profileIds')}
        (staging / 'index.json').unlink()
        write_json(staging / 'index.json', index)
        manifest['files']['index.json'] = hashlib.sha256((staging / 'index.json').read_bytes()).hexdigest()
        (staging / 'manifest.json').unlink()
        write_json(staging / 'manifest.json', manifest)
        print('Verificando integridade de toda a publicação...', flush=True)
        verify_output(staging)
        if backup.exists():
            raise ValueError('Backup anterior existente; verificar recuperação antes de publicar')
        os.replace(destination, backup)
        try:
            os.replace(staging, destination)
        except BaseException:
            os.replace(backup, destination)
            raise
        shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, action='append', default=[], choices=tse.ELECTION_YEARS)
    parser.add_argument('--people', action='store_true', help='Construir o índice de pessoas por identificadores oficiais')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('public/data'))
    args = parser.parse_args()
    if not args.year and not args.people:
        parser.error('Informe --year ou --people')
    refresh_elections(args.output, Client(offline=args.offline), sorted(set(args.year)), include_people=args.people)
    print('Dados eleitorais atualizados e publicação local validada.', flush=True)


if __name__ == '__main__':
    main()

"""Retry handling for incomplete responses from public data APIs."""
import hashlib
import http.client
import io
import json
import tempfile
import unittest
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from pipeline.http import Client


class Response:
    def __init__(self, body):
        self.body = body
        self.headers = {'ETag': '"snapshot"', 'Last-Modified': 'Tue, 06 Oct 2026 00:00:00 GMT'}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


class HttpRetryTests(unittest.TestCase):
    def test_gateway_outage_can_recover_after_four_failed_attempts(self):
        url = 'https://dadosabertos.camara.leg.br/api/v2/deputados?itens=100'
        body = b'{"dados": []}'
        errors = [HTTPError(url, 504, 'Gateway Timeout', None, io.BytesIO(b'timeout')) for _ in range(4)]
        with tempfile.TemporaryDirectory() as directory:
            client = Client(cache=Path(directory))
            with patch('pipeline.http.urlopen', side_effect=[*errors, Response(body)]) as open_url, \
                    patch('pipeline.http.time.sleep') as sleep, self.assertLogs('pipeline.http', level='WARNING') as logs:
                self.assertEqual(client.get(url), body)
            self.assertEqual(open_url.call_count, 5)
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [5, 10, 20, 40])
            self.assertTrue(all(url in message for message in logs.output))
            self.assertTrue(all(error.fp.closed for error in errors))
            self.assertEqual(client.sources[url]['sha256'], hashlib.sha256(body).hexdigest())

    def test_persistent_outage_fails_without_reusing_or_overwriting_old_data(self):
        with tempfile.TemporaryDirectory() as directory:
            url, _body, _metadata = self.seed(directory, days=1)
            before = {path.name: path.read_bytes() for path in Path(directory).iterdir()}
            errors = [HTTPError(url, 504, 'Gateway Timeout', None, io.BytesIO(b'timeout')) for _ in range(6)]
            client = Client(cache=Path(directory))
            with patch('pipeline.http.urlopen', side_effect=errors) as open_url, \
                    patch('pipeline.http.time.sleep') as sleep, self.assertLogs('pipeline.http', level='WARNING'), \
                    self.assertRaises(HTTPError) as raised:
                client.get(url)
            self.assertEqual(raised.exception.code, 504)
            raised.exception.close()
            self.assertEqual(open_url.call_count, 6)
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [5, 10, 20, 40, 60])
            self.assertEqual({path.name: path.read_bytes() for path in Path(directory).iterdir()}, before)
            self.assertNotIn(url, client.sources)

    def test_permanent_http_errors_are_not_retried(self):
        for status in (400, 401, 403, 404):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                url = 'https://example.gov.br/expenses.json'
                error = HTTPError(url, status, 'Unavailable', None, io.BytesIO(b'error'))
                client = Client(cache=Path(directory))
                expected_log = self.assertLogs('pipeline.http', level='ERROR') if status != 404 else nullcontext()
                with patch('pipeline.http.urlopen', side_effect=error) as open_url, \
                        patch('pipeline.http.time.sleep') as sleep, expected_log:
                    with self.assertRaises(HTTPError) as raised:
                        client.get(url)
                raised.exception.close()
                open_url.assert_called_once()
                sleep.assert_not_called()

    def seed(self, directory, days=0, http_status=None):
        url = 'https://example.gov.br/expenses.json'
        body = b'{"data": []}'
        key = hashlib.sha256(url.encode()).hexdigest()
        metadata = {'url': url, 'fetchedAt': (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(),
                    'sha256': hashlib.sha256(body).hexdigest(), 'etag': '"snapshot"'}
        if http_status:
            metadata['httpStatus'] = http_status
        (Path(directory) / key).write_bytes(body)
        (Path(directory) / (key + '.json')).write_text(json.dumps(metadata))
        return url, body, metadata

    def test_historical_cache_preserves_actual_collection_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            url, body, metadata = self.seed(directory, days=364)
            client = Client(cache=Path(directory))
            with patch('pipeline.http.urlopen') as open_url:
                self.assertEqual(client.get(url, cache_days=365), body)
                open_url.assert_not_called()
            self.assertEqual(client.sources[url]['fetchedAt'], metadata['fetchedAt'])
            self.assertTrue(client.sources[url]['cacheReused'])

    def test_expired_history_revalidates_and_updates_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            url, body, metadata = self.seed(directory, days=366)
            client = Client(cache=Path(directory))
            with patch('pipeline.http.urlopen', side_effect=HTTPError(url, 304, 'Not Modified', None, None)) as open_url:
                self.assertEqual(client.get(url, cache_days=365), body)
                self.assertEqual(open_url.call_args.args[0].get_header('If-none-match'), '"snapshot"')
            open_url.side_effect.close()
            self.assertGreater(client.sources[url]['fetchedAt'], metadata['fetchedAt'])

    def test_forced_review_and_recent_years_do_not_skip_http(self):
        for cache_days, forced in ((365, True), (0, False)):
            with self.subTest(cache_days=cache_days, forced=forced), tempfile.TemporaryDirectory() as directory:
                url, body, _metadata = self.seed(directory)
                client = Client(cache=Path(directory), review_history=forced)
                with patch('pipeline.http.urlopen', return_value=Response(body)) as open_url:
                    self.assertEqual(client.get(url, cache_days=cache_days), body)
                    open_url.assert_called_once()
        current_year = datetime.now(timezone.utc).year
        with tempfile.TemporaryDirectory() as directory:
            client = Client(cache=Path(directory))
            self.assertEqual(client.historical_cache_days(current_year), 0)
            self.assertEqual(client.historical_cache_days(current_year - 1), 0)
            self.assertEqual(client.historical_cache_days(current_year - 2), 365)

    def test_reused_404_stays_unavailable_and_corrupt_history_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            url, _body, metadata = self.seed(directory, http_status=404)
            client = Client(cache=Path(directory))
            with patch('pipeline.http.urlopen') as open_url, self.assertRaises(HTTPError) as raised:
                client.get(url, cache_days=365)
            self.assertEqual(raised.exception.code, 404)
            raised.exception.close()
            open_url.assert_not_called()
            self.assertEqual(client.sources[url]['fetchedAt'], metadata['fetchedAt'])
            (Path(directory) / hashlib.sha256(url.encode()).hexdigest()).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'Cache corrompido'):
                client.get(url, cache_days=365)

    def test_incomplete_read_retries_and_only_caches_complete_body(self):
        url = 'https://example.gov.br/expenses.json'
        body = b'{"data": []}'

        with tempfile.TemporaryDirectory() as directory:
            client = Client(cache=Path(directory))
            with patch('pipeline.http.urlopen', side_effect=[
                http.client.IncompleteRead(b'{"data":', 303), Response(body)
            ]) as open_url, patch('pipeline.http.time.sleep'):
                self.assertEqual(client.get(url), body)

            self.assertEqual(open_url.call_count, 2)
            key = hashlib.sha256(url.encode()).hexdigest()
            self.assertEqual((Path(directory) / key).read_bytes(), body)
            metadata = json.loads((Path(directory) / f'{key}.json').read_text())
            self.assertEqual(metadata['sha256'], hashlib.sha256(body).hexdigest())
            self.assertEqual(client.sources[url]['etag'], '"snapshot"')

    def test_remote_disconnect_retries(self):
        url = 'https://example.gov.br/senators/42.json'
        body = b'{"data": []}'

        with tempfile.TemporaryDirectory() as directory:
            client = Client(cache=Path(directory))
            with patch('pipeline.http.urlopen', side_effect=[
                http.client.RemoteDisconnected('Remote end closed connection without response'),
                Response(body)
            ]) as open_url, patch('pipeline.http.time.sleep'):
                self.assertEqual(client.get(url), body)

            self.assertEqual(open_url.call_count, 2)


if __name__ == '__main__':
    unittest.main()

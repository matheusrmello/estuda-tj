import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import catalog
import server
import test_server


class CatalogTest(unittest.TestCase):
    request = test_server.Flow.request

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        server.DATA = Path(self.tmp.name); server.init()
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close(); self.thread.join(); self.tmp.cleanup()

    def test_catalog_import_keeps_official_key_separate_and_deduplicates(self):
        headers = {'Content-Type':'application/json'}
        payload = json.dumps({'id':'tjsp2401-004'})
        with patch.object(catalog, 'fetch_pdf', return_value=test_server.simple_pdf()) as fetch:
            status, result = self.request('POST', '/api/catalog/import', payload, headers)
            self.assertEqual(status, 201)
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(result['exam']['source_info']['kind'], 'prova')
            self.assertEqual(result['answer']['source_info']['kind'], 'gabarito')
            self.assertEqual(result['answer']['status'], 'referencia')
            self.assertEqual(result['exam']['source_info']['version_match'], 'pendente')
            self.assertEqual(self.request('GET', '/api/documents/%s/drafts' % result['answer']['id'])[1], [])
            self.assertEqual(self.request('GET', '/api/questions')[1], [])
            status, again = self.request('POST', '/api/catalog/import', payload, headers)
            self.assertEqual(again['exam']['id'], result['exam']['id'])
            self.assertEqual(again['answer']['id'], result['answer']['id'])

    def test_invalid_id_and_failed_fetch_leave_no_documents(self):
        headers = {'Content-Type':'application/json'}
        with patch.object(catalog, 'fetch_pdf') as fetch:
            self.assertEqual(self.request('POST','/api/catalog/import','{"id":"https://example.com"}',headers)[0], 400)
            fetch.assert_not_called()
        with patch.object(catalog, 'fetch_pdf', side_effect=[test_server.simple_pdf(), catalog.FetchError('indisponível')]):
            self.assertEqual(self.request('POST','/api/catalog/import','{"id":"tjsp2401-004"}',headers)[0], 502)
        self.assertEqual(self.request('GET','/api/documents')[1], [])
        with patch.object(catalog, 'fetch_pdf', side_effect=[test_server.simple_pdf(), b'%PDF-invalid']):
            self.assertEqual(self.request('POST','/api/catalog/import','{"id":"tjsp2401-004"}',headers)[0], 400)
        self.assertEqual(self.request('GET','/api/documents')[1], [])

    def test_catalog_rejects_unlisted_urls(self):
        with self.assertRaises(catalog.FetchError):
            catalog.fetch_pdf('http://127.0.0.1/', 100)


if __name__ == '__main__': unittest.main()

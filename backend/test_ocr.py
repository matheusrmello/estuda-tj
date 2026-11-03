"""Testes de OCR com API OpenAI simulada, sem enviar imagens pela rede."""
import json
import http.client
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from xml.etree import ElementTree as ET

import ocr
import server
from test_server import simple_pdf
from extract import extract_candidates

NS = ocr.NS
CONFIG = {'ESTUDATJ_OCR_ENABLED': '1', 'ESTUDATJ_OCR_MODEL': 'gpt-test', 'OPENAI_API_KEY': 'fake-key'}


def bbox_page(lines):
    page = ET.Element(f'{{{NS}}}page', {'width':'600', 'height':'800'})
    for y, value in enumerate(lines, 1):
        line = ET.SubElement(page, f'{{{NS}}}line', {'xMin':'50', 'yMin':str(40 + y * 20)})
        ET.SubElement(line, f'{{{NS}}}word').text = value
    return page


def bbox(pages):
    root = ET.Element(f'{{{NS}}}html')
    body = ET.SubElement(root, f'{{{NS}}}body')
    for lines in pages:
        body.append(bbox_page(lines))
    return ET.tostring(root, encoding='utf-8')


def blank_pdf(count):
    kids = ' '.join(f'{n + 3} 0 R' for n in range(count))
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               f'<< /Type /Pages /Kids [{kids}] /Count {count} >>'.encode()]
    objects.extend([b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << >> >>'] * count)
    data, offsets = b'%PDF-1.4\n', [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(data)
    data += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    data += b''.join(f'{pos:010d} 00000 n \n'.encode() for pos in offsets[1:])
    return data + f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()


class OCRTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.src = Path(self.temp.name) / 'doc.pdf'
        self.src.write_bytes(b'%PDF-not-needed-by-mocks')

    @patch.dict('os.environ', CONFIG, clear=True)
    @patch('ocr._request_ocr')
    def test_ocr_requires_per_upload_opt_in(self, request):
        pages = [{'page':1, 'text':'Cabecalho'}, {'page':2, 'text':''}]
        original = bbox([['Cabecalho'], []])
        result, out = ocr.process_pages(self.src, pages, original)
        self.assertEqual(out, original)
        self.assertEqual([p['ocr_status'] for p in result], ['nao_solicitado'] * 2)
        self.assertEqual(result[0]['text'], 'Cabecalho')
        request.assert_not_called()

    @patch.dict('os.environ', {}, clear=True)
    @patch('ocr._request_ocr')
    def test_missing_configuration_preserves_short_native_text(self, request):
        pages = [{'page':1, 'text':'Cabeçalho'}, {'page':2, 'text':''}]
        xml = bbox([['Cabeçalho'], []])
        result, out = ocr.process_pages(self.src, pages, xml, enable_ocr=True)
        self.assertEqual(out, xml)
        self.assertEqual([p['ocr_status'] for p in result], ['configuracao_ausente'] * 2)
        self.assertEqual([p['extraction_method'] for p in result], ['pdf_text', 'none'])
        request.assert_not_called()

    @patch.dict('os.environ', dict(CONFIG, ESTUDATJ_OCR_MODEL='astra'), clear=True)
    @patch('ocr._request_ocr')
    def test_forbidden_model_is_not_invoked(self, request):
        result, _ = ocr.process_pages(self.src, [{'page':1, 'text':''}], bbox([[]]), enable_ocr=True)
        self.assertEqual(result[0]['ocr_status'], 'modelo_proibido')
        request.assert_not_called()

    @patch.dict('os.environ', dict(CONFIG, ESTUDATJ_OCR_MODEL='gemini-test'), clear=True)
    @patch('ocr._request_ocr')
    def test_non_openai_model_is_not_invoked(self, request):
        result, _ = ocr.process_pages(self.src, [{'page':1, 'text':''}], bbox([[]]), enable_ocr=True)
        self.assertEqual(result[0]['ocr_status'], 'modelo_proibido')
        request.assert_not_called()

    @patch.dict('os.environ', CONFIG, clear=True)
    @patch('ocr.shutil.which', return_value=None)
    @patch('ocr._request_ocr')
    def test_missing_renderer_is_reported_without_request(self, request, _which):
        result, _ = ocr.process_pages(self.src, [{'page':1, 'text':''}], bbox([[]]), enable_ocr=True)
        self.assertEqual(result[0]['ocr_status'], 'indisponivel')
        request.assert_not_called()

    @patch.dict('os.environ', CONFIG, clear=True)
    @patch('ocr.shutil.which', return_value='/usr/bin/pdftoppm')
    @patch('ocr._ocr_page')
    def test_mixed_document_preserves_native_and_creates_drafts_from_ocr(self, recognize, _which):
        scanned = 'Direito Penal\n01. Pergunta digitalizada?\n(A) Primeira\n(B) Segunda'
        recognize.return_value = scanned
        pages = [{'page':1,'text':'Texto nativo da primeira página suficientemente longo para não precisar de reconhecimento.'},
                 {'page':2,'text':''}, {'page':3,'text':'Texto nativo da última página suficientemente longo para não precisar de reconhecimento.'}]
        xml = bbox([['Texto nativo da primeira página'], [], ['02. Próxima pergunta?', '(A) Sim', '(B) Não']])
        result, output = ocr.process_pages(self.src, pages, xml, enable_ocr=True)
        self.assertEqual([p['extraction_method'] for p in result], ['pdf_text','ocr','pdf_text'])
        self.assertEqual(result[1]['ocr_status'], 'concluido')
        self.assertEqual(result[1]['text'], scanned)
        self.assertEqual(recognize.call_count, 1)
        self.assertEqual(recognize.call_args.args[1], 2)
        candidates = extract_candidates(output)
        self.assertEqual([q['page'] for q in candidates], [2,3])
        self.assertEqual(candidates[0]['options'], ['Primeira', 'Segunda'])
        self.assertTrue(candidates[0]['warnings'])
        values = list(ET.fromstring(output).itertext())
        self.assertIn('Texto nativo da primeira página', values)
        self.assertIn('02. Próxima pergunta?', values)

    @patch.dict('os.environ', CONFIG, clear=True)
    @patch('ocr.shutil.which', return_value='/usr/bin/pdftoppm')
    @patch('ocr._ocr_page', side_effect=URLError('network error'))
    def test_network_failure_keeps_pdf_text_and_does_not_leak_error(self, _recognize, _which):
        pages = [{'page':1, 'text':'Rodapé'}]
        xml = bbox([['Rodapé']])
        result, out = ocr.process_pages(self.src, pages, xml, enable_ocr=True)
        self.assertEqual(result[0]['ocr_status'], 'falhou')
        self.assertEqual(result[0]['text'], 'Rodapé')
        self.assertNotIn('fake-key', str(result))
        self.assertEqual(list(ET.fromstring(out).itertext()), list(ET.fromstring(xml).itertext()))

    @patch.dict('os.environ', CONFIG, clear=True)
    @patch('ocr.shutil.which', return_value='/usr/bin/pdftoppm')
    @patch('ocr._ocr_page', return_value='')
    def test_ocr_limit_and_empty_recognition_are_reported(self, recognize, _which):
        pages = [{'page':number, 'text':''} for number in range(1, ocr.MAX_OCR_PAGES + 2)]
        result, _ = ocr.process_pages(self.src, pages, bbox([[] for _ in pages]), enable_ocr=True)
        self.assertEqual(recognize.call_count, ocr.MAX_OCR_PAGES)
        self.assertTrue(all(p['ocr_status'] == 'sem_texto' for p in result[:-1]))
        self.assertEqual(result[-1]['ocr_status'], 'limite_excedido')

    @patch('ocr.build_opener')
    def test_request_uses_responses_api_and_reads_output_text(self, opener):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, _size):
                return json.dumps({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'01. Enunciado\n(A) Sim'}]}]}).encode()
        opener.return_value.open.return_value = Response()
        result = ocr._request_ocr(b'fake-image', 'gpt-test', 'fake-key', 4)
        self.assertEqual(result, '01. Enunciado\n(A) Sim')
        request = opener.return_value.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, 'https://api.openai.com/v1/responses')
        self.assertFalse(payload['store'])
        self.assertTrue(payload['input'][0]['content'][1]['image_url'].startswith('data:image/png;base64,'))

    @patch.dict('os.environ', CONFIG, clear=True)
    @patch('ocr.shutil.which', return_value='/usr/bin/pdftoppm')
    @patch('ocr._ocr_page', return_value='Língua Portuguesa\n01. Qual opção?\n(A) Sim\n(B) Não')
    def test_http_upload_requires_opt_in_and_exposes_ocr_draft(self, recognize, _which):
        old_data = server.DATA
        server.DATA = Path(self.temp.name) / 'data'
        server.init()
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        def request(method, path, body=None, headers=None):
            conn = http.client.HTTPConnection('127.0.0.1', httpd.server_port)
            try:
                conn.request(method, path, body, headers or {})
                response = conn.getresponse()
                return response.status, json.loads(response.read())
            finally:
                conn.close()
        try:
            status, first = request('POST', '/api/documents', simple_pdf(), {'Content-Type':'application/pdf'})
            self.assertEqual(status, 201)
            self.assertEqual(first['pages'][0]['ocr_status'], 'nao_solicitado')
            recognize.assert_not_called()
            status, doc = request('POST', '/api/documents', simple_pdf(), {'Content-Type':'application/pdf', 'X-Enable-OCR':'true'})
            self.assertEqual(status, 201)
            self.assertEqual(doc['status'], 'em_revisao')
            self.assertEqual(doc['pages'][0]['ocr_status'], 'concluido')
            self.assertEqual(doc['pages'][0]['extraction_method'], 'ocr')
            status, drafts = request('GET', '/api/documents/%s/drafts' % doc['id'])
            self.assertEqual(status, 200)
            self.assertEqual(len(drafts), 1)
            self.assertEqual(drafts[0]['page'], 1)
            self.assertEqual(drafts[0]['status'], 'em_revisao')
            self.assertTrue(drafts[0]['warnings'])
            self.assertNotIn('fake-key', json.dumps(doc))
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join()
            server.DATA = old_data

    @patch.dict('os.environ', CONFIG, clear=True)
    @patch('ocr.shutil.which', return_value='/usr/bin/pdftoppm')
    @patch('ocr._ocr_page')
    def test_continue_batches_preserves_published_question_and_is_idempotent(self, recognize, _which):
        recognize.side_effect = lambda _src, number, _tmp, _model, _key, _timeout: (
            f'Língua Portuguesa\n{number:02d}. Questão da página {number}?\n(A) Sim\n(B) Não')
        old_data = server.DATA
        server.DATA = Path(self.temp.name) / 'data'
        server.init()
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        def request(method, path, body=None, headers=None):
            conn = http.client.HTTPConnection('127.0.0.1', httpd.server_port)
            try:
                conn.request(method, path, body, headers or {})
                response = conn.getresponse()
                return response.status, json.loads(response.read())
            finally:
                conn.close()
        try:
            status, doc = request('POST', '/api/documents', blank_pdf(12), {'Content-Type':'application/pdf', 'X-Enable-OCR':'true'})
            self.assertEqual(status, 201)
            self.assertEqual(len(doc['pages']), 12)
            self.assertEqual(sum(p['ocr_status'] == 'concluido' for p in doc['pages']), ocr.MAX_OCR_PAGES)
            self.assertEqual(recognize.call_count, ocr.MAX_OCR_PAGES)
            doc_id = doc['id']
            route = f'/api/documents/{doc_id}/ocr'
            draft_route = f'/api/documents/{doc_id}/drafts'
            status, drafts = request('GET', draft_route)
            self.assertEqual(status, 200)
            self.assertEqual(len(drafts), 10)
            first = drafts[0]
            status, question = request('POST', f"/api/drafts/{first['id']}/publish", json.dumps({'answer': None, 'prompt': 'Questão revisada por mim'}), {'Content-Type':'application/json'})
            self.assertEqual(status, 201)
            self.assertEqual(question['prompt'], 'Questão revisada por mim')
            status, _ = request('POST', route, json.dumps({'confirm':False}), {'Content-Type':'application/json'})
            self.assertEqual(status, 400)
            self.assertEqual(recognize.call_count, 10)
            status, updated = request('POST', route, json.dumps({'confirm':True}), {'Content-Type':'application/json'})
            self.assertEqual(status, 200)
            self.assertTrue(all(p['ocr_status'] == 'concluido' for p in updated['pages']))
            self.assertEqual(recognize.call_count, 12)
            status, after = request('GET', draft_route)
            self.assertEqual(status, 200)
            self.assertEqual(len(after), 12)
            self.assertEqual(len({d['number'] for d in after}), 12)
            first_after = next(d for d in after if d['id'] == first['id'])
            self.assertEqual(first_after['status'], 'publicada')
            self.assertEqual(first_after['question_id'], question['id'])
            status, questions = request('GET', '/api/questions')
            self.assertEqual(status, 200)
            self.assertEqual(len(questions), 1)
            self.assertEqual(questions[0]['prompt'], 'Questão revisada por mim')
            status, _ = request('POST', route, json.dumps({'confirm':True}), {'Content-Type':'application/json'})
            self.assertEqual(status, 200)
            self.assertEqual(recognize.call_count, 12)
            self.assertEqual(len(request('GET', draft_route)[1]), 12)
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join()
            server.DATA = old_data

    @patch.dict('os.environ', CONFIG, clear=True)
    @patch('ocr.shutil.which', return_value='/usr/bin/pdftoppm')
    @patch('ocr._ocr_page')
    def test_concurrent_continue_does_not_send_the_same_page_twice(self, recognize, _which):
        called = threading.Event()
        release = threading.Event()
        def recognize_page(*_args):
            called.set()
            if not release.wait(3):
                raise RuntimeError('Teste não liberou o OCR')
            return '01. Questão?\n(A) Sim\n(B) Não'
        recognize.side_effect = recognize_page
        old_data = server.DATA
        server.DATA = Path(self.temp.name) / 'data'
        server.init()
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        serving = threading.Thread(target=httpd.serve_forever, daemon=True)
        serving.start()
        def request(method, path, body=None, headers=None):
            conn = http.client.HTTPConnection('127.0.0.1', httpd.server_port, timeout=5)
            try:
                conn.request(method, path, body, headers or {})
                response = conn.getresponse()
                return response.status, json.loads(response.read())
            finally:
                conn.close()
        workers = []
        results = []
        try:
            status, doc = request('POST', '/api/documents', blank_pdf(1), {'Content-Type':'application/pdf'})
            self.assertEqual(status, 201)
            self.assertEqual(doc['pages'][0]['ocr_status'], 'nao_solicitado')
            def continuation():
                results.append(request('POST', f"/api/documents/{doc['id']}/ocr", json.dumps({'confirm':True}), {'Content-Type':'application/json'}))
            first = threading.Thread(target=continuation)
            workers.append(first); first.start()
            self.assertTrue(called.wait(3))
            second = threading.Thread(target=continuation)
            workers.append(second); second.start()
            release.set()
            for worker in workers:
                worker.join(5)
                self.assertFalse(worker.is_alive())
            self.assertEqual([result[0] for result in results], [200, 200])
            self.assertEqual(recognize.call_count, 1)
            self.assertEqual(len(request('GET', f"/api/documents/{doc['id']}/drafts")[1]), 1)
        finally:
            release.set()
            for worker in workers:
                worker.join(5)
            httpd.shutdown(); httpd.server_close(); serving.join()
            server.DATA = old_data

if __name__ == '__main__':
    unittest.main()

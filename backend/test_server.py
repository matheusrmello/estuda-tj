import http.client
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path
from http.server import ThreadingHTTPServer
import server


def simple_pdf():
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>', b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>', b'<< /Length 45 >>\nstream\nBT /F1 12 Tf 20 200 Td (Questao teste) Tj ET\nendstream', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    content = b'%PDF-1.4\n'; offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(content)); content += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(content); content += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    content += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return content + f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()


class Flow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        server.DATA = Path(cls.tmp.name)
        server.init()
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True); cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close(); cls.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse(); result = (response.status, json.loads(response.read()))
        conn.close(); return result

    def test_answer_key_upload_remains_separate(self):
        status, doc = self.request('POST', '/api/documents', simple_pdf(), {'Content-Type': 'application/pdf', 'X-Document-Kind': 'gabarito'})
        self.assertEqual(status, 201)
        self.assertEqual(doc['source_info']['kind'], 'gabarito')
        self.assertEqual(self.request('GET', f"/api/documents/{doc['id']}/drafts")[1], [])
        status, result = self.request('GET', f"/api/documents/{doc['id']}/answer-keys")
        self.assertEqual(status, 200)
        self.assertFalse(result['matched'])
        self.assertEqual(result['versions'], {})

    def test_import_review_answer(self):
        status, document = self.request('POST', '/api/documents', simple_pdf(), {'Content-Type': 'application/pdf', 'X-Filename': 'prova.pdf'})
        self.assertEqual(status, 201); self.assertEqual(document['status'], 'em_revisao')
        self.assertIn('Questao teste', document['pages'][0]['text'])
        body = {'document_id': document['id'], 'page': 1, 'number': '1', 'subject': 'Teste', 'prompt': 'Enunciado revisado', 'options': ['Sim', 'Não'], 'answer': 0, 'answer_source': 'Gabarito fornecido pelo usuário'}
        status, q = self.request('POST', '/api/questions', json.dumps(body), {'Content-Type': 'application/json'})
        self.assertEqual(status, 201); self.assertNotIn('answer', q)
        status, result = self.request('POST', '/api/attempts', json.dumps({'question_id': q['id'], 'selected': 1}), {'Content-Type': 'application/json'})
        self.assertEqual(status, 201); self.assertEqual(result['correct'], 0); self.assertEqual(result['answer'], 0)
        self.assertEqual(len(self.request('GET', '/api/attempts')[1]), 1)
        body['page'] = 2
        self.assertEqual(self.request('POST', '/api/questions', json.dumps(body), {'Content-Type': 'application/json'})[0], 400)

    def test_reject_invalid_pdf_and_origin(self):
        self.assertEqual(self.request('POST', '/api/documents', b'not a pdf', {'Content-Type': 'application/pdf'})[0], 400)
        self.assertEqual(self.request('GET', '/api/questions', headers={'Origin': 'https://example.com'})[0], 403)

    def test_page_preview_renders_and_rejects_missing_page(self):
        status, doc = self.request('POST', '/api/documents', simple_pdf(), {'Content-Type': 'application/pdf'})
        self.assertEqual(status, 201)
        conn = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port)
        conn.request('GET', '/api/documents/%d/pages/1.png' % doc['id'])
        response = conn.getresponse(); image = response.read()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader('Content-Type'), 'image/png')
        self.assertTrue(image.startswith(b'\x89PNG\r\n\x1a\n'))
        conn.close()
        self.assertEqual(self.request('GET', '/api/documents/%d/pages/2.png' % doc['id'])[0], 404)

    def test_question_excerpt_is_returned_as_image(self):
        _, doc = self.request('POST', '/api/documents', simple_pdf(), {'Content-Type':'application/pdf'})
        payload = {'document_id':doc['id'],'page':1,'number':'1','subject':'Teste','prompt':'Pergunta','options':['Sim','Não'],'answer':None}
        _, question = self.request('POST','/api/questions',json.dumps(payload),{'Content-Type':'application/json'})
        with patch.object(server, 'question_region', return_value=[.1,.1,.8,.7]):
            conn = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port)
            conn.request('GET',f"/api/questions/{question['id']}/excerpt.png")
            response = conn.getresponse(); image=response.read(); conn.close()
            self.assertEqual(response.status,200)
            self.assertTrue(image.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_illustration_is_bound_to_pdf_and_question(self):
        status, doc = self.request('POST', '/api/documents', simple_pdf(), {'Content-Type': 'application/pdf'})
        self.assertEqual(status, 201)
        body = {'document_id': doc['id'], 'page': 1, 'number': '01', 'subject': 'Teste', 'prompt': 'Pergunta', 'options': ['A', 'B'], 'answer': None, 'answer_source': ''}
        status, q = self.request('POST', '/api/questions', json.dumps(body), {'Content-Type': 'application/json'})
        self.assertEqual(status, 201)
        url = '/api/questions/%d/illustration.png' % q['id']
        self.assertEqual(self.request('GET', url)[0], 404)
        with patch.object(server, 'ILLUSTRATED_PDF', doc['sha256']), patch.object(server, 'ILLUSTRATIONS', {1: (1, 0, 0, 500, 500)}):
            items = self.request('GET', '/api/questions')[1]
            self.assertEqual(next(item for item in items if item['id'] == q['id'])['illustration']['page'], 1)
            conn = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port)
            conn.request('GET', url); response = conn.getresponse(); data = response.read()
            self.assertEqual(response.status, 200)
            self.assertTrue(data.startswith(b'\x89PNG\r\n\x1a\n'))
            conn.close()

    def test_publish_draft_without_answer(self):
        status, doc = self.request('POST', '/api/documents', simple_pdf(), {'Content-Type':'application/pdf'})
        self.assertEqual(status, 201)
        candidate = {'page': 1, 'number': '1', 'subject': 'Teste', 'prompt': 'Pergunta?', 'options': ['Sim', 'Não'], 'context': 'Texto de apoio', 'warnings': ['Revisar']}
        with server.connect() as db:
            draft_id = db.execute('INSERT INTO drafts(document_id,data) VALUES(?,?)', (doc['id'], json.dumps(candidate))).lastrowid
        self.assertEqual(len(self.request('GET', '/api/documents/%d/drafts' % doc['id'])[1]), 1)
        route = '/api/drafts/%d/publish' % draft_id
        status, question = self.request('POST', route, json.dumps({'answer': None}), {'Content-Type':'application/json'})
        self.assertEqual(status, 201)
        self.assertEqual(question['context'], 'Texto de apoio')
        self.assertEqual(self.request('POST', route, '{}', {'Content-Type':'application/json'})[0], 400)
        status, attempt = self.request('POST', '/api/attempts', json.dumps({'question_id':question['id'], 'selected':0}), {'Content-Type':'application/json'})
        self.assertEqual(status, 201)
        self.assertIsNone(attempt['correct']); self.assertIsNone(attempt['answer'])
        self.assertIsNone(self.request('GET', '/api/attempts')[1][0]['correct'])


if __name__ == '__main__': unittest.main()

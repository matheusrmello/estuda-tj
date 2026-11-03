import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from unittest.mock import MagicMock
import test_server
import server


class BatchReviewTest(unittest.TestCase):
    request = test_server.Flow.request

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        server.DATA = Path(self.tmp.name)
        server.init()
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close(); self.thread.join(); self.tmp.cleanup()

    def test_batch_review_and_publish_without_gabarito(self):
        status, doc = self.request('POST', '/api/documents', test_server.simple_pdf(), {'Content-Type': 'application/pdf'})
        self.assertEqual(status, 201)
        def candidate(number, options):
            return {'page': 1, 'number': number, 'subject': 'Teste', 'prompt': 'Pergunta?', 'options': options, 'context': '', 'context_page': None}
        with server.connect() as db:
            a = db.execute('INSERT INTO drafts(document_id,data) VALUES(?,?)', (doc['id'], json.dumps(candidate('1', ['a','b','c','d','e'])))).lastrowid
            b = db.execute('INSERT INTO drafts(document_id,data) VALUES(?,?)', (doc['id'], json.dumps(candidate('2', ['a','b'])))).lastrowid
        endpoint = '/api/documents/%s/batch-review' % doc['id']
        self.assertEqual(self.request('POST', endpoint, json.dumps({'page':1}), {'Content-Type':'application/json'})[0], 400)
        with patch.object(server.settings_ai, 'review_page', return_value={a:{'ok':True,'motivo':''}, b:{'ok':True,'motivo':''}}):
            status, _ = self.request('POST', endpoint, json.dumps({'page':1,'confirm':True}), {'Content-Type':'application/json'})
        self.assertEqual(status, 200)
        drafts = self.request('GET', '/api/documents/%s/drafts' % doc['id'])[1]
        states = {d['id']: d['batch_review']['status'] for d in drafts}
        self.assertEqual(states[a], 'sem_alerta'); self.assertEqual(states[b], 'atencao')
        pub = '/api/documents/%s/batch-publish' % doc['id']
        self.assertEqual(self.request('POST', pub, '{}', {'Content-Type':'application/json'})[0], 400)
        self.assertEqual(self.request('POST', pub, '{"confirm":true}', {'Content-Type':'application/json'})[1]['published'], 1)
        self.assertEqual(self.request('POST', pub, '{"confirm":true}', {'Content-Type':'application/json'})[1]['published'], 0)
        question = next(q for q in self.request('GET', '/api/questions')[1] if q['document_id'] == doc['id'])
        self.assertEqual(question['review_method'], 'automatico')
        status, result = self.request('POST', '/api/attempts', json.dumps({'question_id':question['id'], 'selected':0}), {'Content-Type':'application/json'})
        self.assertEqual(status, 201); self.assertIsNone(result['correct'])

    def test_failed_review_does_not_mark_ready(self):
        _, doc = self.request('POST', '/api/documents', test_server.simple_pdf(), {'Content-Type':'application/pdf'})
        item = {'page':1,'number':'1','subject':'Teste','prompt':'Pergunta?', 'options':['a','b','c','d','e']}
        with server.connect() as db: db.execute('INSERT INTO drafts(document_id,data) VALUES(?,?)', (doc['id'], json.dumps(item)))
        with patch.object(server.settings_ai, 'review_page', side_effect=server.settings_ai.TutorError('Falha')):
            status, _ = self.request('POST', '/api/documents/%s/batch-review' % doc['id'], '{"page":1,"confirm":true}', {'Content-Type':'application/json'})
        self.assertEqual(status, 502)
        drafts = self.request('GET', '/api/documents/%s/drafts' % doc['id'])[1]
        self.assertNotIn('batch_review', drafts[0])

    def test_visual_review_rejects_missing_or_duplicate_ids(self):
        import settings_ai
        settings_ai.update_settings(server.DATA, {'ai_provider':'deepseek', 'deepseek_model':'deepseek-flash', 'deepseek_api_key':'test-key'})
        answer = {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'items':[{'id':1,'ok':True,'motivo':''}, {'id':1,'ok':True,'motivo':''}]})}}]}
        response = MagicMock(); response.read.return_value = json.dumps(answer).encode()
        opener = MagicMock(); opener.open.return_value.__enter__.return_value = response
        with patch.object(settings_ai, 'build_opener', return_value=opener):
            with self.assertRaises(settings_ai.TutorError):
                settings_ai.review_page(server.DATA, b'fake-image', [{'id':1}, {'id':2}])
        settings_ai.update_settings(server.DATA, {'clear_deepseek_api_key': True})


if __name__ == '__main__': unittest.main()

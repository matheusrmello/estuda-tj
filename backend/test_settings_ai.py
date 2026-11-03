import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import settings_ai as ai

class TestSettingsAndTutor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        ai._api_key = ''
        self.addCleanup(setattr, ai, '_api_key', '')
        self.item = {'subject':'Português', 'number':'1', 'prompt':'O que significa?', 'context':'', 'options':['A','B'], 'answer':-1, 'answer_source':'', 'page':3}

    def test_settings_do_not_write_or_return_key_and_removal(self):
        result = ai.update_settings(self.tmp.name, {'ai_provider':'deepseek','deepseek_model':'deepseek-flash','daily_goal':10,'deepseek_api_key':'fake-secret'})
        self.assertTrue(result['deepseek_key_configured'])
        self.assertNotIn('fake-secret', json.dumps(result))
        path = Path(self.tmp.name) / 'settings.json'
        self.assertNotIn('fake-secret', path.read_text())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(ai.update_settings(self.tmp.name, {'deepseek_api_key':''})['deepseek_key_configured'])
        self.assertFalse(ai.update_settings(self.tmp.name, {'clear_deepseek_api_key':True})['deepseek_key_configured'])
        ai.update_settings(self.tmp.name, {'deepseek_api_key':'fake-secret'})
        ai._api_key = ''
        self.assertFalse(ai.get_settings(self.tmp.name)['deepseek_key_configured'])
        self.assertEqual(ai.get_settings(self.tmp.name)['daily_goal'],10)

    def test_validation_and_inactive(self):
        for data in ({'ai_provider':'bad'}, {'daily_goal':True}, {'daily_goal':1001}, {'deepseek_model':'gpt-6-astra'}, {'deepseek_api_key':'abc\ndef'}, {'deepseek_api_key':'x','clear_deepseek_api_key':True}):
            with self.subTest(data=data), self.assertRaises(ValueError): ai.update_settings(self.tmp.name, data)
        with self.assertRaises(ValueError): ai.ask(self.tmp.name, self.item, '')

    @patch('settings_ai.build_opener')
    def test_chat_request_and_no_external_error_leak(self, opener):
        ai.update_settings(self.tmp.name, {'ai_provider':'deepseek', 'deepseek_api_key':'fake-secret'})
        response = opener.return_value.open.return_value.__enter__.return_value
        response.read.return_value = json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'Resposta de teste.'}}]}).encode()
        out = ai.ask(self.tmp.name, self.item, 'Explique')
        self.assertEqual(out['answer'],'Resposta de teste.')
        args, kwargs = opener.return_value.open.call_args
        request = args[0]
        self.assertEqual(request.full_url,'https://api.deepseek.com/chat/completions')
        payload = json.loads(request.data)
        self.assertEqual(payload['model'],'deepseek-flash')
        self.assertEqual(payload['thinking'], {'type':'disabled'})
        self.assertIn('não confiável',payload['messages'][0]['content'])
        self.assertIn('Explique',payload['messages'][1]['content'])
        opener.return_value.open.side_effect = OSError('fake-secret provider response')
        with self.assertRaises(ai.TutorError) as cm: ai.ask(self.tmp.name, self.item, '')
        self.assertNotIn('fake-secret',str(cm.exception))

if __name__ == '__main__': unittest.main()

class TestSettingsHTTP(unittest.TestCase):
    def test_http_settings_and_tutor(self):
        import http.client
        import threading
        from http.server import ThreadingHTTPServer
        import server
        with tempfile.TemporaryDirectory() as tmp:
            original_data = server.DATA
            server.DATA = Path(tmp)
            ai._api_key = ''
            server.init()
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            def request(method,path,data=None):
                c=http.client.HTTPConnection('127.0.0.1',httpd.server_port)
                c.request(method,path,body=json.dumps(data) if data is not None else None,headers={'Content-Type':'application/json'} if data is not None else {})
                r=c.getresponse(); result=(r.status,json.loads(r.read())); c.close(); return result
            try:
                status,result=request('POST','/api/settings',{'ai_provider':'deepseek','deepseek_api_key':'fake-key'})
                self.assertEqual(status,200); self.assertTrue(result['deepseek_key_configured']); self.assertNotIn('fake-key',json.dumps(result))
                self.assertNotIn('fake-key',json.dumps(request('GET','/api/settings')))
                self.assertEqual(request('POST','/api/tutor',{'question_id':900})[0],400)
                with server.connect() as db:
                    doc=db.execute("INSERT INTO documents(filename,sha256,status,pages,created_at) VALUES('x.pdf','x','em_revisao','[]','now')").lastrowid
                    qid=db.execute("INSERT INTO questions(document_id,page,number,subject,prompt,options,answer,answer_source,created_at) VALUES(?,1,'1','teste','questao','[\"A\",\"B\"]',-1,'','now')",(doc,)).lastrowid
                with patch('settings_ai.ask',return_value={'answer':'ok','provider':'deepseek','model':'deepseek-flash'}) as ask:
                    status,output=request('POST','/api/tutor',{'question_id':qid})
                    self.assertEqual(status,200); self.assertEqual(output['answer'],'ok'); self.assertEqual(ask.call_args.args[1]['options'],['A','B'])
            finally:
                httpd.shutdown(); httpd.server_close(); thread.join(); server.DATA=original_data; ai._api_key=''

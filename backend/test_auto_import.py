import http.client
import json
import subprocess
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import server
from test_server import Flow, simple_pdf


class AutomaticImport(unittest.TestCase):
    setUpClass = classmethod(Flow.setUpClass.__func__)
    tearDownClass = classmethod(Flow.tearDownClass.__func__)
    request = Flow.request

    def test_crop_padding_stays_inside_page(self):
        self.assertEqual(server.padded_crop([0, 0, 1, 1], 1000, 2000), (0, 0, 1000, 2000))
        x, y, width, height = server.padded_crop([.121,.472,.302,.536], 1400, 2000)
        self.assertLess(y, int(.472 * 2000))
        self.assertGreater(y + height, int(.536 * 2000))
    def test_auto_import_publishes_graphical_question_and_crops(self):
        item = {'numero':'92','materia':'Direito','enunciado':'Escolha a figura','contexto':'',
                'alternativas':[{'letra':'A','texto':'','imagem':[0.1,0.2,0.4,0.5]},
                                {'letra':'B','texto':'Outra','imagem':None}], 'imagens':[]}
        config = {'ai_provider':'deepseek','deepseek_key_configured':True,'deepseek_model':'deepseek-flash'}
        draft = {'number':'92','page':1,'prompt':'Escolha a figura','subject':'Lógica','options':['A','B'],'context':'Texto de apoio compartilhado','context_page':1,'warnings':[]}
        with patch.object(server.settings_ai, 'get_settings', return_value=config), patch.object(server.settings_ai, 'extract_page', return_value=[item]), patch.object(server, 'extract_candidates', return_value=[draft]):
            status, doc = self.request('POST','/api/documents',simple_pdf(),{'Content-Type':'application/pdf','X-Auto-Extract':'true'})
            self.assertEqual(status,201)
            for _ in range(100):
                _, job = self.request('GET', f"/api/documents/{doc['id']}/import-job")
                if job['status'] != 'processando': break
                time.sleep(.05)
            self.assertEqual(job['status'],'concluido',job)
        questions = self.request('GET','/api/questions')[1]
        q = next(q for q in questions if q['document_id']==doc['id'])
        self.assertEqual(q['review_method'],'ia_extracao')
        self.assertEqual(q['subject'],'Lógica')
        self.assertEqual(q['context'], 'Texto de apoio compartilhado')
        self.assertEqual(q['visual_assets']['options'][0], [0.1,0.2,0.4,0.5])
        conn = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port)
        conn.request('GET',f"/api/questions/{q['id']}/assets/option/0.png")
        response = conn.getresponse(); image=response.read(); conn.close()
        self.assertEqual(response.status,200)
        self.assertTrue(image.startswith(b'\x89PNG\r\n\x1a\n'))
        status, attempt = self.request('POST','/api/attempts',json.dumps({'question_id':q['id'],'selected':0}),{'Content-Type':'application/json'})
        self.assertEqual(status,201); self.assertIsNone(attempt['correct'])

    def test_auto_import_requires_configured_vision(self):
        config = {'ai_provider':'deepseek','deepseek_key_configured':False,'deepseek_model':'deepseek-flash'}
        with patch.object(server.settings_ai, 'get_settings', return_value=config):
            status, _ = self.request('POST','/api/documents',simple_pdf(),{'Content-Type':'application/pdf','X-Auto-Extract':'true'})
            self.assertEqual(status,400)

    def test_failure_does_not_publish_invented_questions(self):
        config = {'ai_provider':'deepseek','deepseek_key_configured':True,'deepseek_model':'deepseek-flash'}
        with patch.object(server.settings_ai, 'get_settings', return_value=config), patch.object(server.settings_ai, 'extract_page', side_effect=server.settings_ai.TutorError('indisponível')) as extract:
            status, doc = self.request('POST','/api/documents',simple_pdf(),{'Content-Type':'application/pdf','X-Auto-Extract':'true'})
            self.assertEqual(status,201)
            for _ in range(100):
                _, job = self.request('GET', f"/api/documents/{doc['id']}/import-job")
                if job['status'] != 'processando': break
                time.sleep(.05)
            self.assertEqual(job['status'],'falhou')
            self.assertFalse(any(q['document_id']==doc['id'] for q in self.request('GET','/api/questions')[1]))
            extract.side_effect = None
            extract.return_value = [{'numero':'1','materia':'Teste','enunciado':'Pergunta?', 'contexto':'', 'imagens':[], 'alternativas':[{'letra':'A','texto':'Sim','imagem':None},{'letra':'B','texto':'Não','imagem':None}]}]
            status, _ = self.request('POST', f"/api/documents/{doc['id']}/resume-import", '{}', {'Content-Type':'application/json'})
            self.assertEqual(status,202)
            for _ in range(100):
                _, job = self.request('GET', f"/api/documents/{doc['id']}/import-job")
                if job['status'] != 'processando': break
                time.sleep(.05)
            self.assertEqual(job['status'],'concluido',job)
            self.assertEqual(sum(q['document_id']==doc['id'] for q in self.request('GET','/api/questions')[1]),1)

    def test_resume_skips_completed_pages(self):
        directory = Path(self.tmp.name)
        first, second, combined = directory/'first.pdf', directory/'second.pdf', directory/'two-pages.pdf'
        first.write_bytes(simple_pdf()); second.write_bytes(simple_pdf())
        subprocess.run(['pdfunite',str(first),str(second),str(combined)], check=True, capture_output=True)
        def item(number):
            return {'numero':str(number),'materia':'Teste','enunciado':'Pergunta?', 'contexto':'','imagens':[], 'alternativas':[{'letra':'A','texto':'Sim','imagem':None},{'letra':'B','texto':'Não','imagem':None}]}
        config = {'ai_provider':'deepseek','deepseek_key_configured':True,'deepseek_model':'deepseek-flash'}
        with patch.object(server.settings_ai, 'get_settings', return_value=config), patch.object(server.settings_ai, 'extract_page', side_effect=[[item(1)],server.settings_ai.TutorError('erro'),server.settings_ai.TutorError('erro')]) as extract:
            status, doc = self.request('POST','/api/documents',combined.read_bytes(),{'Content-Type':'application/pdf','X-Auto-Extract':'true'})
            self.assertEqual(status,201)
            for _ in range(100):
                _, job = self.request('GET', f"/api/documents/{doc['id']}/import-job")
                if job['status'] != 'processando': break
                time.sleep(.05)
            self.assertEqual(job['status'],'parcial',job)
            extract.reset_mock(); extract.side_effect = None; extract.return_value = [item(2)]
            status, _ = self.request('POST', f"/api/documents/{doc['id']}/resume-import", '{}', {'Content-Type':'application/json'})
            self.assertEqual(status,202)
            for _ in range(100):
                _, job = self.request('GET', f"/api/documents/{doc['id']}/import-job")
                if job['status'] != 'processando': break
                time.sleep(.05)
            self.assertEqual(job['status'],'concluido',job)
            self.assertEqual(extract.call_count,1)
            self.assertEqual(sorted(int(q['number']) for q in self.request('GET','/api/questions')[1] if q['document_id']==doc['id']),[1,2])

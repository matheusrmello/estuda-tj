import json
import unittest
import test_server
import server


class SimulationFlow(unittest.TestCase):
    setUpClass = classmethod(test_server.Flow.setUpClass.__func__)
    tearDownClass = classmethod(test_server.Flow.tearDownClass.__func__)
    request = test_server.Flow.request

    def post(self, path, data):
        return self.request('POST', path, json.dumps(data), {'Content-Type':'application/json'})

    def make_questions(self, subject, answers):
        status, doc = self.request('POST','/api/documents',test_server.simple_pdf(),{'Content-Type':'application/pdf'})
        self.assertEqual(status,201)
        result = []
        for index, answer in enumerate(answers):
            status, q = self.post('/api/questions', {'document_id':doc['id'],'page':1,'number':str(index+1),'subject':subject,'prompt':f'Pergunta {index+1}', 'options':['Sim','Não'], 'answer':answer,'answer_source':'Gabarito de teste' if answer is not None else ''})
            self.assertEqual(status,201); result.append(q['id'])
        return result

    def test_create_resume_and_finish_distinguishes_outcomes(self):
        ids = self.make_questions('Simulado integrado', [0,0,None,0])
        self.assertEqual(self.post('/api/simulations',{'quantidade':5,'duracao_minutos':10,'materia':'Simulado integrado'})[0],400)
        status, sim = self.post('/api/simulations',{'quantidade':4,'duracao_minutos':10,'materia':'Simulado integrado'})
        self.assertEqual(status,201)
        self.assertTrue(all('answer' not in item and 'answer_source' not in item for item in sim['questions']))
        route = f"/api/simulations/{sim['id']}"
        for qid, selected in [(ids[0],0),(ids[1],1),(ids[2],0)]:
            self.assertEqual(self.post(route+'/answer',{'question_id':qid,'selected':selected})[0],200)
        self.assertEqual(self.post(route+'/answer',{'question_id':999999,'selected':0})[0],400)
        status, resumed = self.request('GET',route)
        self.assertEqual(status,200)
        self.assertEqual(sum(q['selected'] is not None for q in resumed['questions']),3)
        with server.connect() as db:
            db.execute('UPDATE questions SET answer=1 WHERE id=?',(ids[0],))
        status, result = self.post(route+'/finish',{})
        self.assertEqual(status,200)
        self.assertEqual(result['result'], {'acertos':1,'erros':1,'sem_gabarito':1,'nao_respondidas':1})
        self.assertEqual(self.post(route+'/answer',{'question_id':ids[3],'selected':0})[0],409)
        self.assertEqual(self.post(route+'/finish',{})[1]['result'],result['result'])

    def test_expiration_is_enforced_and_persisted(self):
        qid = self.make_questions('Simulado vencido',[0])[0]
        status, sim = self.post('/api/simulations',{'quantidade':1,'duracao_minutos':1,'materia':'Simulado vencido'})
        self.assertEqual(status,201)
        with server.connect() as db:
            db.execute("UPDATE simulations SET deadline='2000-01-01T00:00:00+00:00' WHERE id=?",(sim['id'],))
        route=f"/api/simulations/{sim['id']}"
        self.assertEqual(self.post(route+'/answer',{'question_id':qid,'selected':0})[0],409)
        _, result=self.request('GET',route)
        self.assertEqual(result['status'],'finalizado')
        self.assertEqual(result['result']['nao_respondidas'],1)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM simulations WHERE id=?',(sim['id'],)).fetchone()['status'],'finalizado')

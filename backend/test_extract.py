import unittest
from extract import extract_candidates, append_line, question_region

class ExtractTest(unittest.TestCase):
    def test_question_region_excludes_the_next_question(self):
        lines = ['01. Pergunta?', '(A) Sim', '(B) Não', '02. Outra pergunta?', '(A) Sim', '(B) Não']
        body = ''.join('<line xMin="20" yMin="%d"><word>%s</word></line>' % (40 + i * 20, value) for i, value in enumerate(lines))
        xml = ('<html xmlns="http://www.w3.org/1999/xhtml"><body><page width="600" height="800">' + body + '</page></body></html>').encode()
        region = question_region(xml, '01')
        self.assertIsNotNone(region)
        self.assertLess(region[3], 100 / 800)
        self.assertIsNone(question_region(xml, '99'))
    def test_joins_wrapped_words_but_keeps_evident_compounds(self):
        self.assertEqual(append_line('compleição físi-', 'ca do bandido'), 'compleição física do bandido')
        self.assertEqual(append_line('norma-pa-', 'drão'), 'norma-padrão')
        self.assertEqual(append_line('ex-', 'marido'), 'ex-marido')
        self.assertEqual(append_line('tratá-', 'los'), 'tratá-los')

    def test_reconstructs_words_within_prompt_and_options(self):
        lines = ['01. Pergunta sobre a compleição físi-', 'ca?', '(A) Descrição minuci-', 'osa.', '(B) Alternativa seguinte.']
        body = ''.join('<line xMin="20" yMin="%d"><word>%s</word></line>' % (40 + i * 20, value) for i, value in enumerate(lines))
        xml = ('<html xmlns="http://www.w3.org/1999/xhtml"><body><page width="600" height="800">' + body + '</page></body></html>').encode()
        q = extract_candidates(xml)[0]
        self.assertEqual(q['prompt'], 'Pergunta sobre a compleição física?')
        self.assertEqual(q['options'], ['Descrição minuciosa.', 'Alternativa seguinte.'])

    def test_cover_number_does_not_consume_shared_context(self):
        def page(lines):
            body = ''.join('<line xMin="20" yMin="%d"><word>%s</word></line>' % (40 + i * 20, value) for i, value in enumerate(lines))
            return '<page width="600" height="800">' + body + '</page>'
        xml = ('<html xmlns="http://www.w3.org/1999/xhtml"><body>' + page(['004. Prova Objetiva', 'Instruções gerais']) + page(['Língua Portuguesa', 'Leia a tira para as questões de números 01 e 02.', 'Texto da tira.', '01. Primeira?', '(A) Sim', '(B) Não', '02. Segunda?', '(A) Sim', '(B) Não']) + '</body></html>').encode()
        questions = extract_candidates(xml)
        self.assertEqual([q['number'] for q in questions], ['01', '02'])
        self.assertTrue(all('Texto da tira.' in q['context'] and q['context_page'] == 2 for q in questions))
        self.assertNotIn('Instruções gerais', questions[0]['context'])

    def test_image_only_alternatives_remain_visible_for_review(self):
        lines = ['92. Selecione o diagrama correto:', '(A)', '(B)', '(C)', '(D)', '(E)']
        body = ''.join('<line xMin="20" yMin="%d"><word>%s</word></line>' % (40 + i * 20, value) for i, value in enumerate(lines))
        xml = ('<html xmlns="http://www.w3.org/1999/xhtml"><body><page width="600" height="800">' + body + '</page></body></html>').encode()
        question = extract_candidates(xml)[0]
        self.assertEqual(question['number'], '92')
        self.assertEqual(question['options'], ['', '', '', '', ''])
        self.assertTrue(any('Alternativas sem texto' in warning for warning in question['warnings']))

    def test_removes_scratch_area_appended_after_last_option(self):
        lines = ['01. Quanto é?', '(A) 1', '(B) 2', '(C) 3', '(D) 4', '(E) 5', 'R', 'A S', 'C', 'U', 'N', 'H', 'O']
        body = ''.join('<line xMin="20" yMin="%d"><word>%s</word></line>' % (40 + i * 20, value) for i, value in enumerate(lines))
        xml = ('<html xmlns="http://www.w3.org/1999/xhtml"><body><page width="600" height="800">' + body + '</page></body></html>').encode()
        self.assertEqual(extract_candidates(xml)[0]['options'][-1], '5')

    def test_columns_subjects_context_and_incomplete(self):
        def line(x,y,text):
            return '<line xMin="%s" yMin="%s"><word>%s</word></line>' % (x,y,text)
        left = [(10,10,'Língua Portuguesa'),(10,20,'Leia o texto para as questões de números 01 a 02.'),(10,30,'Texto de apoio.'),(10,40,'01. Primeira questão?'),(10,50,'(A) Uma'),(10,60,'(B) Outra'),(10,70,'02. Segunda questão?'),(10,80,'(A) Sim'),(10,90,'(B) Não')]
        right = [(300,10,'D ireito P enal'),(300,20,'03. Terceira questão?'),(300,30,'(A) Certo'),(300,40,'(B) Errado')]
        xml = ('<html xmlns="http://www.w3.org/1999/xhtml"><body><page width="600" height="800">'+''.join(line(*x) for x in [(x,y+20,t) for x,y,t in left+right])+'</page></body></html>').encode()
        questions=extract_candidates(xml)
        self.assertEqual([q['number'] for q in questions], ['01','02','03'])
        self.assertEqual(questions[2]['subject'], 'Direito Penal')
        self.assertEqual(questions[0]['options'], ['Uma','Outra'])
        self.assertIn('Texto de apoio', questions[1]['context'])
        self.assertEqual(questions[1]['context_page'], 1)
        self.assertTrue(questions[0]['warnings'])

if __name__=='__main__': unittest.main()

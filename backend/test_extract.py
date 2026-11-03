import unittest
from extract import extract_candidates

class ExtractTest(unittest.TestCase):
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

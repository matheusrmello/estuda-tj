import unittest
from settings_ai import validate_extraction


class VisualExtractionTests(unittest.TestCase):
    def sample(self):
        return {'questoes': [{'numero': '92', 'materia': 'Raciocínio Lógico', 'enunciado': 'Escolha o diagrama.', 'contexto': '', 'alternativas': [{'letra': 'A', 'texto': '', 'imagem': [0.1, 0.2, 0.4, 0.3]}, {'letra': 'B', 'texto': 'Outro', 'imagem': None}], 'imagens': []}]}

    def test_image_alternative_is_accepted(self):
        self.assertEqual(validate_extraction(self.sample())[0]['numero'], '92')

    def test_invalid_boxes_empty_options_and_duplicates_fail(self):
        value = self.sample(); value['questoes'][0]['alternativas'][0]['imagem'] = [0.8, 0.2, 0.4, 0.3]
        with self.assertRaises(ValueError): validate_extraction(value)
        value = self.sample(); value['questoes'][0]['alternativas'][0]['imagem'] = None
        with self.assertRaises(ValueError): validate_extraction(value)
        value = self.sample(); value['questoes'].append(value['questoes'][0])
        with self.assertRaises(ValueError): validate_extraction(value)

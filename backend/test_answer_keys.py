import unittest

from answer_keys import extract_versions, selected_versions


class AnswerKeyExtraction(unittest.TestCase):
    def test_versions_continue_on_next_page_and_keep_annulments(self):
        result = extract_versions(['VERSÃO 1\n1 - A 2 - N', '3 - E\nVERSÃO 2\n1 - B'])
        self.assertEqual(result['1']['answers'], {1: 'A', 2: 'N', 3: 'E'})
        self.assertEqual(result['1']['pages'], [1, 2])
        self.assertEqual(result['2']['answers'], {1: 'B'})

    def test_conflicting_entries_are_flagged(self):
        result = extract_versions(['VERSÃO 1\n1 - A 1 - B'])
        self.assertEqual(result['1']['conflicts'], [1])

    def test_no_version_is_not_assumed(self):
        self.assertEqual(extract_versions(['1 - A 2 - B']), {})

    def test_2024_reapplication_only_keeps_versions_1_and_3(self):
        pages = ['TJSP2401 CAPITAL prova 24 de novembro de 2024\nVERSÃO 1\n1 - A\nVERSÃO 2\n1 - B\nVERSÃO 3\n1 - C\nVERSÃO 4\n1 - D']
        versions = extract_versions(pages)
        self.assertEqual(set(selected_versions(pages, versions)), {'1', '3'})
        self.assertEqual(set(selected_versions(['TJSP2401 CAPITAL prova 8 de setembro de 2024'], versions)), {'1', '2', '3', '4'})


if __name__ == '__main__':
    unittest.main()

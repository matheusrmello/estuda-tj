"""Extração heurística: produz somente candidatos sujeitos a revisão humana."""
import re
import unicodedata
from xml.etree import ElementTree


def norm(value):
    value = re.sub(r'\b([A-ZÀ-Ú])\s+(?=[a-zà-ú])', r'\1', value)
    return ''.join(c for c in unicodedata.normalize('NFKD', value.lower()) if not unicodedata.combining(c)).strip()

SUBJECTS = {norm(x): x for x in (
    'Língua Portuguesa', 'Direito Penal', 'Direito Processual Penal',
    'Direito Processual Civil', 'Direito Constitucional', 'Direito Administrativo',
    'Normas da Corregedoria Geral da Justiça', 'Atualidades', 'Matemática',
    'Informática', 'Raciocínio Lógico', 'Conhecimentos em Direito', 'Conhecimentos Gerais')}


def page_lines(xml):
    xml = re.sub(rb'[\x00-\x08\x0b\x0c\x0e-\x1f]', b'', xml)
    root = ElementTree.fromstring(xml)
    ns = {'h': 'http://www.w3.org/1999/xhtml'}
    for page in root.findall('.//h:page', ns):
        width, height = float(page.get('width')), float(page.get('height'))
        lines = []
        for line in page.findall('.//h:line', ns):
            words = line.findall('h:word', ns)
            if not words: continue
            x, y = float(line.get('xMin')), float(line.get('yMin'))
            text = ' '.join(''.join(w.itertext()) for w in words).strip()
            if not text or y > height * .96 or y < height * .015: continue
            if re.search(r'TJSP\d+[/\-]|Confidencial até o momento da aplicação', text, re.I): continue
            lines.append((x, y, text))
        # Só ordenar como colunas se há texto independente em ambos os lados.
        left = [l for l in lines if l[0] < width * .49]
        right = [l for l in lines if l[0] >= width * .49]
        if len(left) >= 4 and len(right) >= 4:
            lines = sorted(left, key=lambda x: x[1]) + sorted(right, key=lambda x: x[1])
        else:
            lines.sort(key=lambda x: (x[1], x[0]))
        yield [line[2] for line in lines]


def extract_candidates(xml):
    candidates, current, subject = [], None, 'Não identificada'
    pending_context, shared, context_page = [], [], None
    def finish():
        nonlocal current
        if not current: return
        if len(current['options']) >= 2 and current['prompt'].strip():
            current['prompt'] = current['prompt'].strip()
            current['options'] = [x.strip() for x in current['options']]
            current['warnings'] = ['Rascunho automático: revise enunciado, alternativas, matéria e contexto no PDF original.', 'Imagens e textos de apoio podem não ter sido extraídos.']
            if len(current['options']) != 5: current['warnings'].append('Quantidade de alternativas incomum ou incompleta.')
            candidates.append(current)
        current = None
    for page_no, lines in enumerate(page_lines(xml), 1):
        for line in lines:
            clean = line.strip()
            n = norm(clean)
            if n in SUBJECTS:
                subject = SUBJECTS[n]; continue
            # Cabeçalhos ou textos de apoio após as opções não devem ser fundidos à última alternativa.
            qmatch = re.match(r'^(\d{1,3})\s*[.)]\s+(.+)$', clean)
            if qmatch and 1 <= int(qmatch.group(1)) <= 200:
                finish()
                number = int(qmatch.group(1))
                context = '\n'.join(pending_context)[-30000:]
                match = re.search(r'questões?\s+(?:de\s+)?números?\s+(\d+)\s+(?:a|e)\s+(\d+)', context, re.I)
                if match:
                    shared.append((int(match.group(1)), int(match.group(2)), context, context_page))
                if not context:
                    match_shared = next(((value, source_page) for start, end, value, source_page in reversed(shared) if start <= number <= end), ('', None))
                    context, context_page = match_shared
                current = {'page': page_no, 'number': qmatch.group(1), 'subject': subject, 'prompt': qmatch.group(2), 'options': [], 'context': context, 'context_page': context_page}
                pending_context = []
                context_page = None
                continue
            option = re.match(r'^\(?([A-E])\)\s*(.+)$', clean)
            if current and option:
                letter = ord(option.group(1)) - 65
                if letter == len(current['options']):
                    current['options'].append(option.group(2)); continue
            if current:
                if len(current['options']) == 5 and (re.match(r'^(Leia|Observe|Considere|Para responder|As questões)', clean, re.I) or pending_context):
                    if not pending_context: context_page = page_no
                    pending_context.append(clean)
                elif current['options']:
                    current['options'][-1] += ' ' + clean
                else:
                    current['prompt'] += ' ' + clean
            elif clean:
                if not pending_context: context_page = page_no
                pending_context.append(clean)
    finish()
    return candidates

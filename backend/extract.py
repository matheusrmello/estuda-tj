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


def append_line(existing, line):
    """Reconstitui palavras divididas na mudança de linha, preservando hífens evidentes."""
    match = re.search(r'([^\W\d_]+)-$', existing, re.UNICODE)
    start = re.match(r'([a-zà-ú]+)\b', line)
    if match and start:
        previous, following = match.group(1), start.group(1)
        prefixes = {'ex', 'pré', 'pós', 'pró', 'vice', 'anti', 'auto', 'semi', 'super', 'inter', 'intra', 'micro', 'macro', 'não'}
        clitics = {'me', 'te', 'se', 'nos', 'vos', 'lhe', 'lhes', 'lo', 'la', 'los', 'las'}
        if previous.lower() not in prefixes and not (following in clitics and (previous.endswith(('r', 's', 'z')) or previous[-1] in 'áéíóúâêôãõ')):
            return existing[:-1] + line
        return existing + line
    return existing + ' ' + line


def question_region(xml, number):
    """Estima a região de uma questão em uma página nativa de PDF."""
    if not str(number).isdigit():
        return None
    try:
        root = ElementTree.fromstring(xml)
        ns = {'h': 'http://www.w3.org/1999/xhtml'}
        page = root.find('.//h:page', ns)
        width, height = float(page.get('width')), float(page.get('height'))
        lines = []
        for line in page.findall('.//h:line', ns):
            text = ' '.join(''.join(word.itertext()) for word in line.findall('h:word', ns)).strip()
            x, y = float(line.get('xMin')), float(line.get('yMin'))
            if text and height * .015 <= y < height * .96:
                lines.append((x, y, text))
        left = sum(1 for x, _, _ in lines if x < width * .49)
        right = sum(1 for x, _, _ in lines if x >= width * .49)
        two_columns = left >= 4 and right >= 4
        starts = []
        for x, y, text in lines:
            match = re.match(r'^(\d{1,3})\s*[.)]\s+', text)
            if match:
                starts.append((int(match.group(1)), x, y))
        matches = [(x,y) for n,x,y in starts if n == int(number)]
        if len(matches) != 1:
            return None
        x, y = matches[0]
        right_col = two_columns and x >= width * .49
        same_column = lambda px: not two_columns or (px >= width * .49) == right_col
        next_y = min((sy for n,sx,sy in starts if sy > y and same_column(sx)), default=height * .95)
        if next_y <= y + 4:
            return None
        x0, x1 = ((.49, .99) if right_col else (.01, .49)) if two_columns else (.01, .99)
        return [x0, max(.01, (y - 5) / height), x1, min(.96, (next_y - 3) / height)]
    except (ElementTree.ParseError, AttributeError, ValueError, TypeError):
        return None


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
        if current['options'] and current['prompt'].strip():
            current['prompt'] = current['prompt'].strip()
            current['options'] = [re.sub(r'\s+R\s+A\s+S\s+C\s+U\s+N\s+H\s+O\s*$', '', x, flags=re.I).strip() for x in current['options']]
            current['warnings'] = ['Rascunho automático: revise enunciado, alternativas, matéria e contexto no PDF original.', 'Imagens e textos de apoio podem não ter sido extraídos.']
            if len(current['options']) != 5: current['warnings'].append('Quantidade de alternativas incomum ou incompleta.')
            if any(not option for option in current['options']): current['warnings'].append('Alternativas sem texto: podem conter imagens; confira a página original. Não publique sem completar as alternativas.')
            candidates.append(current)
        current = None
    for page_no, lines in enumerate(page_lines(xml), 1):
        for line in lines:
            clean = line.strip()
            if re.fullmatch(r'R\s*A\s*S\s*C\s*U\s*N\s*H\s*O', clean, re.I):
                continue
            n = norm(clean)
            if n in SUBJECTS:
                subject = SUBJECTS[n]
                if current is None:
                    pending_context, context_page = [], None
                continue
            # Cabeçalhos ou textos de apoio após as opções não devem ser fundidos à última alternativa.
            qmatch = re.match(r'^(\d{1,3})\s*[.)]\s+(.+)$', clean)
            if qmatch and re.match(r'^prova\s+objetiva\b', qmatch.group(2), re.I):
                continue
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
            option = re.match(r'^\(?([A-E])\)\s*(.*)$', clean)
            if current and option:
                letter = ord(option.group(1)) - 65
                if letter == len(current['options']):
                    current['options'].append(option.group(2)); continue
            if current:
                if len(current['options']) == 5 and (re.match(r'^(Leia|Observe|Considere|Para responder|As questões)', clean, re.I) or pending_context):
                    if not pending_context: context_page = page_no
                    pending_context.append(clean)
                elif current['options']:
                    current['options'][-1] = append_line(current['options'][-1], clean)
                else:
                    current['prompt'] = append_line(current['prompt'], clean)
            elif clean:
                if not pending_context: context_page = page_no
                pending_context.append(clean)
    finish()
    return candidates

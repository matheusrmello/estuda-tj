"""Leitura conservadora de tabelas de gabarito; não associa versões à prova."""
import re

VERSION = re.compile(r'^\s*VERS[ÃA]O\s+(\d+)\s*$', re.I | re.M)
ENTRY = re.compile(r'(?<!\w)(\d{1,3})\s*[-–]\s*([A-E]|N)(?!\w)', re.I)


def extract_versions(pages):
    """Retorna versões candidatas com página e conflitos, sem presumir validade."""
    versions = {}
    current = None
    for page_no, text in enumerate(pages, 1):
        chunks = VERSION.split(text)
        for i, chunk in enumerate(chunks):
            if i % 2:
                current = chunk
                versions.setdefault(current, {'answers': {}, 'conflicts': [], 'pages': []})
            elif current is not None:
                version = versions[current]
                for match in ENTRY.finditer(chunk):
                    number, answer = int(match.group(1)), match.group(2).upper()
                    if not 1 <= number <= 500:
                        continue
                    if page_no not in version['pages']:
                        version['pages'].append(page_no)
                    existing = version['answers'].get(number)
                    if existing is not None and existing != answer:
                        if number not in version['conflicts']:
                            version['conflicts'].append(number)
                    else:
                        version['answers'][number] = answer
    return versions


def selected_versions(pages, versions):
    """Aplica a seleção do usuário à reaplicação da Capital de 2024."""
    text = ' '.join(pages)
    is_target = (re.search(r'\bTJSP2401\b', text, re.I)
                 and re.search(r'\bCAPITAL\b', text, re.I)
                 and re.search(r'\b24\s+de\s+novembro\s+de\s+2024\b', text, re.I))
    if not is_target:
        return versions
    return {key: value for key, value in versions.items() if key in ('1', '3')}

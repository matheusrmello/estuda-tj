"""Catálogo explícito de fontes oficiais. Não aceita URLs fornecidas pelo cliente."""
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

CATALOG = {
    'tjsp2401-004': {
        'id': 'tjsp2401-004', 'title': 'TJSP 2024 — Escrevente, Capital — caderno 004',
        'description': 'Prova e gabarito definitivo para consulta. A correspondência entre a versão do caderno e a do gabarito ainda não foi confirmada.',
        'exam_url': 'https://documento.vunesp.com.br/documento/stream/NjU5NjQ4Ng==',
        'answer_url': 'https://documento.vunesp.com.br/documento/stream/NjY2ODM2OA==',
        'contest_url': 'https://www.vunesp.com.br/TJSP2401',
        'exam_name': 'TJSP2401-caderno-004.pdf', 'answer_name': 'TJSP2401-gabarito-definitivo.pdf',
    }
}

class FetchError(Exception):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def fetch_pdf(url, limit):
    # Apenas URLs codificadas no catálogo são aceitas; não seguir redirecionamentos.
    if url not in {v[k] for v in CATALOG.values() for k in ('exam_url', 'answer_url')}:
        raise FetchError('Fonte não autorizada.')
    try:
        req = Request(url, headers={'User-Agent': 'EstudaTJ/1.0', 'Accept': 'application/pdf'})
        with build_opener(NoRedirect()).open(req, timeout=30) as response:
            content = response.read(limit + 1)
        if len(content) > limit or not content.startswith(b'%PDF-'):
            raise FetchError('A fonte não retornou um PDF válido dentro do limite.')
        return content
    except HTTPError as exc:
        if exc.code == 403:
            raise FetchError('A Vunesp recusou a busca automática (HTTP 403). Acesse a fonte oficial e use o envio manual.') from exc
        raise FetchError('A fonte oficial retornou um erro HTTP.') from exc
    except (OSError, URLError) as exc:
        raise FetchError('Não foi possível acessar a fonte oficial.') from exc

#!/usr/bin/env python3
"""Servidor local do EstudaTJ. Extração automática é sempre rascunho."""
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from extract import extract_candidates
from ocr import process_pages
import settings_ai

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('ESTUDATJ_DATA', str(ROOT / 'data'))).resolve()
MAX_PDF = 20 * 1024 * 1024
MAX_JSON = 256 * 1024

# Recortes verificados visualmente na prova fornecida pelo usuário. Coordenadas
# são relativas à página renderizada com -scale-to 1600; não se aplicam a outros PDFs.
ILLUSTRATED_PDF = '81c5d124fc15839d4c6271908df962fb54d906c698fa035019144fb35f6f6418'
ILLUSTRATIONS = {
    1: (3, 60, 190, 495, 455), 2: (3, 60, 190, 495, 455),
    12: (5, 580, 95, 495, 650),
    **{n: (8, 60, 100, 495, 660) for n in (21, 22, 23, 24)},
}

def illustration_for(digest, number):
    if digest != ILLUSTRATED_PDF or not re.fullmatch(r'0*\d{1,3}', str(number)):
        return None
    return ILLUSTRATIONS.get(int(number))
OCR_CONTINUATION_LOCK = threading.Lock()


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    db = sqlite3.connect(DATA / 'estudatj.sqlite3', timeout=10, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def init():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    (DATA / 'pdfs').mkdir(exist_ok=True, mode=0o700)
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, filename TEXT NOT NULL, sha256 TEXT NOT NULL, status TEXT NOT NULL, pages TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id), page INTEGER NOT NULL, number TEXT NOT NULL, subject TEXT NOT NULL, prompt TEXT NOT NULL, options TEXT NOT NULL, answer INTEGER NOT NULL, answer_source TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, question_id INTEGER NOT NULL REFERENCES questions(id), selected INTEGER NOT NULL, correct INTEGER NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS drafts(id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id), data TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'em_revisao', question_id INTEGER REFERENCES questions(id));
        ''')
        if 'context' not in [r['name'] for r in db.execute('PRAGMA table_info(questions)')]:
            db.execute("ALTER TABLE questions ADD COLUMN context TEXT NOT NULL DEFAULT ''")
        if 'context_page' not in [r['name'] for r in db.execute('PRAGMA table_info(questions)')]:
            db.execute('ALTER TABLE questions ADD COLUMN context_page INTEGER')


def document(row):
    obj = dict(row)
    obj['pages'] = json.loads(obj['pages'])
    return obj


def question(row):
    obj = dict(row)
    obj['options'] = json.loads(obj['options'])
    # Gabarito não é revelado antes de responder.
    obj.pop('answer')
    return obj

def draft(row):
    result = json.loads(row['data'])
    result.update(id=row['id'], document_id=row['document_id'], status=row['status'], question_id=row['question_id'])
    return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def body(self, limit):
        length = self.headers.get('Content-Length', '')
        if not length.isdigit() or int(length) <= 0 or int(length) > limit:
            raise ValueError('Tamanho de conteúdo inválido ou excedido.')
        return self.rfile.read(int(length))

    def permitted(self):
        host = self.headers.get('Host', '').split(':')[0].lower()
        origin = self.headers.get('Origin')
        if host not in ('localhost', '127.0.0.1'):
            return False
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1') or parsed.netloc != self.headers.get('Host'):
                return False
        return True

    def do_GET(self):
        if not self.permitted():
            return self.send_json(403, {'error': 'Acesso permitido somente localmente.'})
        path = urlsplit(self.path).path
        if path == '/api/settings':
            try:
                return self.send_json(200, settings_ai.get_settings(DATA))
            except settings_ai.TutorError as exc:
                return self.send_json(500, {'error': str(exc)})
        static = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path in static:
            name, mime = static[path]
            try:
                content = (ROOT.parent / 'frontend' / name).read_bytes()
            except OSError:
                return self.send_json(404, {'error': 'Interface não encontrada.'})
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(content)
            return
        with connect() as db:
            illustrated = re.fullmatch(r'/api/questions/(\d+)/illustration\.png', path)
            if illustrated:
                row = db.execute('SELECT q.number, d.sha256 FROM questions q JOIN documents d ON d.id=q.document_id WHERE q.id=?', (int(illustrated[1]),)).fetchone()
                crop = illustration_for(row['sha256'], row['number']) if row else None
                if not crop:
                    return self.send_json(404, {'error': 'Imagem não encontrada para esta questão.'})
                page_no, x, y, width, height = crop
                try:
                    with tempfile.TemporaryDirectory(dir=DATA) as tmp:
                        prefix = str(Path(tmp) / 'illustration')
                        source = DATA / 'pdfs' / (row['sha256'] + '.pdf')
                        result = subprocess.run(['pdftoppm', '-f', str(page_no), '-l', str(page_no), '-singlefile', '-scale-to', '1600', '-x', str(x), '-y', str(y), '-W', str(width), '-H', str(height), '-png', str(source), prefix], capture_output=True, timeout=20, check=False)
                        if result.returncode: raise OSError('Falha ao renderizar recorte')
                        content = Path(prefix + '.png').read_bytes()
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/png')
                    self.send_header('Content-Length', str(len(content)))
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except (OSError, subprocess.SubprocessError):
                    return self.send_json(500, {'error': 'Não foi possível mostrar o recorte.'})
            preview = re.fullmatch(r'/api/documents/(\d+)/pages/(\d+)\.png', path)
            if preview:
                doc_id, page_no = map(int, preview.groups())
                row = db.execute('SELECT sha256, pages FROM documents WHERE id=?', (doc_id,)).fetchone()
                if not row or not 1 <= page_no <= len(json.loads(row['pages'])):
                    return self.send_json(404, {'error': 'Documento ou página não encontrado.'})
                source = DATA / 'pdfs' / (row['sha256'] + '.pdf')
                try:
                    with tempfile.TemporaryDirectory(dir=DATA) as tmp:
                        prefix = str(Path(tmp) / 'page')
                        result = subprocess.run(['pdftoppm', '-f', str(page_no), '-l', str(page_no), '-singlefile', '-scale-to', '1600', '-png', str(source), prefix], capture_output=True, timeout=20, check=False)
                        if result.returncode:
                            raise OSError('Falha ao renderizar página')
                        content = Path(prefix + '.png').read_bytes()
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/png')
                    self.send_header('Content-Length', str(len(content)))
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except (OSError, subprocess.SubprocessError):
                    return self.send_json(500, {'error': 'Não foi possível mostrar a página do PDF.'})
            match = re.fullmatch(r'/api/documents/(\d+)/(drafts|pdf)', path)
            if match:
                doc_id = int(match[1]); kind = match[2]
                row = db.execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone()
                if not row: return self.send_json(404, {'error': 'Documento não encontrado.'})
                if kind == 'drafts':
                    return self.send_json(200, [draft(r) for r in db.execute('SELECT * FROM drafts WHERE document_id=? ORDER BY id', (doc_id,))])
                try: content = (DATA / 'pdfs' / (row['sha256'] + '.pdf')).read_bytes()
                except OSError: return self.send_json(404, {'error': 'PDF não encontrado.'})
                self.send_response(200); self.send_header('Content-Type', 'application/pdf'); self.send_header('Content-Length', str(len(content))); self.send_header('Content-Disposition', 'inline'); self.send_header('X-Content-Type-Options', 'nosniff'); self.end_headers(); self.wfile.write(content); return
            if path == '/api/documents':
                return self.send_json(200, [document(r) for r in db.execute('SELECT * FROM documents ORDER BY id DESC')])
            match = re.fullmatch(r'/api/documents/(\d+)', path)
            if match:
                row = db.execute('SELECT * FROM documents WHERE id=?', (int(match[1]),)).fetchone()
                return self.send_json(200, document(row)) if row else self.send_json(404, {'error': 'Documento não encontrado.'})
            if path == '/api/questions':
                questions = []
                for row in db.execute('SELECT q.*, d.sha256 AS document_sha256 FROM questions q JOIN documents d ON d.id=q.document_id ORDER BY q.id DESC'):
                    item = question(row)
                    digest = item.pop('document_sha256')
                    crop = illustration_for(digest, item['number'])
                    if crop:
                        item['illustration'] = {'page': crop[0], 'url': '/api/questions/%d/illustration.png' % item['id']}
                    questions.append(item)
                return self.send_json(200, questions)
            if path == '/api/attempts':
                attempts = [dict(r) for r in db.execute('SELECT * FROM attempts ORDER BY id DESC')]
                for item in attempts:
                    if item['correct'] == -1: item['correct'] = None
                return self.send_json(200, attempts)
        return self.send_json(404, {'error': 'Rota não encontrada.'})

    def do_POST(self):
        if not self.permitted():
            return self.send_json(403, {'error': 'Acesso permitido somente localmente.'})
        path = urlsplit(self.path).path
        try:
            if path == '/api/documents':
                self.upload()
            elif path in ('/api/questions', '/api/attempts', '/api/settings', '/api/tutor') or re.fullmatch(r'/api/drafts/\d+/publish', path) or re.fullmatch(r'/api/documents/\d+/ocr', path):
                if self.headers.get_content_type() != 'application/json':
                    raise ValueError('Use application/json.')
                data = json.loads(self.body(MAX_JSON))
                if not isinstance(data, dict):
                    raise ValueError('JSON deve ser um objeto.')
                if path == '/api/settings': self.send_json(200, settings_ai.update_settings(DATA, data))
                elif path == '/api/tutor': self.tutor(data)
                elif path == '/api/questions': self.add_question(data)
                elif path == '/api/attempts': self.add_attempt(data)
                elif path.startswith('/api/drafts/'): self.publish_draft(int(path.split('/')[3]), data)
                else: self.continue_ocr(int(path.split('/')[3]), data)
            else:
                self.send_json(404, {'error': 'Rota não encontrada.'})
        except settings_ai.TutorError as exc:
            self.send_json(502, {'error': str(exc)})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.send_json(400, {'error': str(exc) or 'Dados inválidos.'})
        except (OSError, subprocess.SubprocessError, sqlite3.Error):
            self.send_json(500, {'error': 'Falha ao processar a solicitação.'})

    def tutor(self, data):
        qid = data.get('question_id')
        if type(qid) is not int or qid <= 0 or set(data) - {'question_id', 'question'}:
            raise ValueError('Questão inválida.')
        with connect() as db:
            row = db.execute('SELECT * FROM questions WHERE id=?', (qid,)).fetchone()
        if row is None: raise ValueError('Questão não encontrada.')
        item = dict(row)
        item['options'] = json.loads(item['options'])
        self.send_json(200, settings_ai.ask(DATA, item, data.get('question', '')))

    def upload(self):
        if self.headers.get_content_type() != 'application/pdf':
            raise ValueError('Envie um PDF com Content-Type application/pdf.')
        content = self.body(MAX_PDF)
        if not content.startswith(b'%PDF-'):
            raise ValueError('Arquivo não possui assinatura PDF válida.')
        filename = Path(unquote(self.headers.get('X-Filename', 'documento.pdf')).replace('\\', '/')).name[:200]
        if not filename or any(ord(c) < 32 for c in filename):
            raise ValueError('Nome de arquivo inválido.')
        digest = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory(dir=DATA) as tmp:
            src = Path(tmp) / 'source.pdf'
            src.write_bytes(content)
            result = subprocess.run(['pdftotext', '-layout', str(src), '-'], capture_output=True, timeout=30, check=False)
            if result.returncode != 0:
                raise ValueError('Não foi possível ler o PDF. Verifique se está válido e sem senha.')
            raw_pages = result.stdout.decode('utf-8', errors='replace').split('\f')
            if raw_pages and not raw_pages[-1].strip(): raw_pages.pop()
            if not raw_pages or len(raw_pages) > 500 or len(result.stdout) > 10 * 1024 * 1024:
                raise ValueError('PDF vazio ou excede os limites de extração.')
            pages = [{'page': i + 1, 'text': page.strip()} for i, page in enumerate(raw_pages)]
            bbox = subprocess.run(['pdftotext', '-bbox-layout', str(src), '-'], capture_output=True, timeout=30, check=False)
            bbox_xml = bbox.stdout if bbox.returncode == 0 and len(bbox.stdout) <= 40 * 1024 * 1024 else b''
            pages, bbox_xml = process_pages(src, pages, bbox_xml, enable_ocr=self.headers.get('X-Enable-OCR', '').lower() == 'true')
            try:
                candidates = extract_candidates(bbox_xml) if bbox_xml else []
            except Exception:
                # O PDF continua disponível para revisão manual se a análise estruturada falhar.
                candidates = []
            for candidate in candidates:
                for n in {candidate['page'], candidate.get('context_page')}:
                    if n and 1 <= n <= len(pages) and pages[n-1]['extraction_method'] == 'ocr':
                        candidate['warnings'].append('Esta questão ou seu contexto contém texto de OCR; confira cuidadosamente no PDF original.')
                        break
            target = DATA / 'pdfs' / (digest + '.pdf')
            if not target.exists():
                target.write_bytes(content)
                target.chmod(0o600)
        with connect() as db:
            cur = db.execute('INSERT INTO documents(filename,sha256,status,pages,created_at) VALUES(?,?,?,?,?)', (filename, digest, 'em_revisao', json.dumps(pages, ensure_ascii=False), now()))
            db.executemany('INSERT INTO drafts(document_id,data) VALUES(?,?)', [(cur.lastrowid, json.dumps(c, ensure_ascii=False)) for c in candidates])
            row = db.execute('SELECT * FROM documents WHERE id=?', (cur.lastrowid,)).fetchone()
        self.send_json(201, document(row))

    def continue_ocr(self, doc_id, data):
        if data.get('confirm') is not True:
            raise ValueError('Confirme o envio das páginas para OCR.')
        with OCR_CONTINUATION_LOCK:
            with connect() as db:
                row = db.execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone()
                if not row: raise ValueError('Documento não encontrado.')
                pages = json.loads(row['pages'])
                # Priorizar páginas ainda não enviadas antes de repetir falhas de OCR.
                pending = ('nao_solicitado', 'limite_excedido', 'configuracao_ausente', 'modelo_proibido', 'indisponivel', 'falhou')
                selected = []
                for status in pending:
                    for page in pages:
                        state = page.get('ocr_status')
                        if state is None and len(re.sub(r'\s+', '', page.get('text', ''))) < 40:
                            state = 'nao_solicitado'
                        if state == status:
                            selected.append(page['page'])
                if not selected:
                    return self.send_json(200, document(row))
                source = DATA / 'pdfs' / (row['sha256'] + '.pdf')
                previous = {(item['page'], str(item['number']).lstrip('0') or '0') for item in
                            [json.loads(r['data']) for r in db.execute('SELECT data FROM drafts WHERE document_id=?', (doc_id,))]}
                previous.update((r['page'], str(r['number']).lstrip('0') or '0') for r in db.execute('SELECT page,number FROM questions WHERE document_id=?', (doc_id,)))
            with tempfile.TemporaryDirectory(dir=DATA) as tmp:
                src = Path(tmp) / 'source.pdf'
                src.write_bytes(source.read_bytes())
                bbox = subprocess.run(['pdftotext', '-bbox-layout', str(src), '-'], capture_output=True, timeout=30, check=False)
                bbox_xml = bbox.stdout if bbox.returncode == 0 and len(bbox.stdout) <= 40 * 1024 * 1024 else b''
                pages, bbox_xml = process_pages(src, pages, bbox_xml, enable_ocr=True, selected_pages=selected)
                try:
                    candidates = extract_candidates(bbox_xml) if bbox_xml else []
                except Exception:
                    candidates = []
            completed = {p['page'] for p in pages if p.get('ocr_status') == 'concluido' and p['page'] in selected}
            ocr_pages = {p['page'] for p in pages if p.get('extraction_method') == 'ocr'}
            additions = []
            for candidate in candidates:
                key = (candidate['page'], str(candidate['number']).lstrip('0') or '0')
                # Uma questão pode começar em um lote anterior e só se tornar
                # reconhecível quando a página seguinte tiver sido processada.
                if not completed or candidate['page'] not in ocr_pages or key in previous:
                    continue
                candidate['warnings'].append('Esta questão ou seu contexto contém texto de OCR; confira cuidadosamente no PDF original.')
                additions.append((doc_id, json.dumps(candidate, ensure_ascii=False)))
                previous.add(key)
            with connect() as db:
                db.execute('UPDATE documents SET pages=? WHERE id=?', (json.dumps(pages, ensure_ascii=False), doc_id))
                db.executemany('INSERT INTO drafts(document_id,data) VALUES(?,?)', additions)
                updated = db.execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone()
            self.send_json(200, document(updated))

    def publish_draft(self, draft_id, data):
        with connect() as db:
            row = db.execute('SELECT * FROM drafts WHERE id=?', (draft_id,)).fetchone()
        if not row: raise ValueError('Rascunho não encontrado.')
        if row['status'] != 'em_revisao': raise ValueError('Rascunho já publicado.')
        original = draft(row)
        allowed = ('page', 'number', 'subject', 'prompt', 'options', 'context', 'context_page', 'answer', 'answer_source')
        original.update({key: data[key] for key in allowed if key in data})
        original['document_id'] = row['document_id']
        self.add_question(original, draft_id)

    def add_question(self, data, draft_id=None):
        doc_id = data['document_id']; page = data['page']; answer = data.get('answer')
        opts = data['options']
        if any(type(v) is not int for v in (doc_id, page)) or not isinstance(opts, list) or not 2 <= len(opts) <= 10 or not all(isinstance(x, str) and 0 < len(x.strip()) <= 5000 for x in opts) or (answer is not None and (type(answer) is not int or not 0 <= answer < len(opts))):
            raise ValueError('Questão, página, alternativas ou resposta inválidas.')
        values = []
        for key in ('number', 'subject', 'prompt'):
            value = data.get(key, '')
            if not isinstance(value, str) or not value.strip() or len(value) > 10000:
                raise ValueError('Preencha número, matéria, enunciado e origem do gabarito.')
            values.append(value.strip())
        source = data.get('answer_source', '')
        context = data.get('context', '')
        context_page = data.get('context_page')
        if not isinstance(source, str) or len(source) > 10000 or (answer is not None and not source.strip()) or not isinstance(context, str) or len(context) > 30000:
            raise ValueError('Informe a origem do gabarito e confira o texto de apoio.')
        with connect() as db:
            if draft_id is not None:
                # Serializa a aprovação para não publicar o mesmo rascunho duas vezes.
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT status FROM drafts WHERE id=?', (draft_id,)).fetchone()
                if not row or row['status'] != 'em_revisao': raise ValueError('Rascunho já publicado ou inexistente.')
            doc = db.execute('SELECT pages FROM documents WHERE id=?', (doc_id,)).fetchone()
            if not doc or not 1 <= page <= len(json.loads(doc['pages'])):
                raise ValueError('Documento ou página não encontrado.')
            if context_page is not None and (type(context_page) is not int or not 1 <= context_page <= len(json.loads(doc['pages']))):
                raise ValueError('Página do texto de apoio inválida.')
            cur = db.execute('INSERT INTO questions(document_id,page,number,subject,prompt,options,answer,answer_source,created_at,context,context_page) VALUES(?,?,?,?,?,?,?,?,?,?,?)', (doc_id, page, *values, json.dumps([x.strip() for x in opts], ensure_ascii=False), answer if answer is not None else -1, source.strip(), now(), context, context_page))
            if draft_id is not None:
                db.execute("UPDATE drafts SET status='publicada', question_id=? WHERE id=?", (cur.lastrowid, draft_id))
            row = db.execute('SELECT * FROM questions WHERE id=?', (cur.lastrowid,)).fetchone()
        self.send_json(201, question(row))

    def add_attempt(self, data):
        qid, selected = data['question_id'], data['selected']
        if type(qid) is not int or type(selected) is not int:
            raise ValueError('Questão ou alternativa inválida.')
        with connect() as db:
            row = db.execute('SELECT * FROM questions WHERE id=?', (qid,)).fetchone()
            if not row or not 0 <= selected < len(json.loads(row['options'])):
                raise ValueError('Questão ou alternativa não encontrada.')
            correct = int(selected == row['answer']) if row['answer'] >= 0 else -1
            cur = db.execute('INSERT INTO attempts(question_id,selected,correct,created_at) VALUES(?,?,?,?)', (qid, selected, correct, now()))
            attempt = dict(db.execute('SELECT * FROM attempts WHERE id=?', (cur.lastrowid,)).fetchone())
            attempt['answer'] = row['answer'] if row['answer'] >= 0 else None
            if correct == -1: attempt['correct'] = None
            attempt['answer_source'] = row['answer_source']
        self.send_json(201, attempt)


if __name__ == '__main__':
    init()
    ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('ESTUDATJ_PORT', '8000'))), Handler).serve_forever()

#!/usr/bin/env python3
"""Servidor local do EstudaTJ. Extração automática é sempre rascunho."""
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import struct
import tempfile
import threading
from datetime import datetime, timezone
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from extract import extract_candidates, question_region
from ocr import process_pages
import settings_ai
import catalog
import answer_keys
import simulados

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


def padded_crop(rect, width, height):
    """Adiciona margem aos retângulos visuais, sem sair da página."""
    x = int(max(0, rect[0] - .012) * width)
    y = int(max(0, rect[1] - .020) * height)
    right = int(min(1, rect[2] + .012) * width)
    bottom = int(min(1, rect[3] + .008) * height)
    return x, y, max(1, right - x), max(1, bottom - y)
OCR_CONTINUATION_LOCK = threading.Lock()
BATCH_REVIEW_LOCK = threading.Lock()


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
        CREATE TABLE IF NOT EXISTS import_jobs(document_id INTEGER PRIMARY KEY REFERENCES documents(id), status TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL, error TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS import_pages(document_id INTEGER NOT NULL REFERENCES documents(id), page INTEGER NOT NULL, status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', PRIMARY KEY(document_id,page));
        CREATE TABLE IF NOT EXISTS simulations(id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, deadline TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, subject TEXT NOT NULL, questions TEXT NOT NULL, responses TEXT NOT NULL);
        ''')
        if 'context' not in [r['name'] for r in db.execute('PRAGMA table_info(questions)')]:
            db.execute("ALTER TABLE questions ADD COLUMN context TEXT NOT NULL DEFAULT ''")
        if 'context_page' not in [r['name'] for r in db.execute('PRAGMA table_info(questions)')]:
            db.execute('ALTER TABLE questions ADD COLUMN context_page INTEGER')
        if 'review_method' not in [r['name'] for r in db.execute('PRAGMA table_info(questions)')]:
            db.execute("ALTER TABLE questions ADD COLUMN review_method TEXT NOT NULL DEFAULT 'manual'")
        if 'source_info' not in [r['name'] for r in db.execute('PRAGMA table_info(documents)')]:
            db.execute("ALTER TABLE documents ADD COLUMN source_info TEXT NOT NULL DEFAULT '{}'")
        if 'visual_assets' not in [r['name'] for r in db.execute('PRAGMA table_info(questions)')]:
            db.execute("ALTER TABLE questions ADD COLUMN visual_assets TEXT NOT NULL DEFAULT '{}'")
        db.execute("UPDATE import_jobs SET status='interrompido', error='Servidor reiniciado durante a importação.' WHERE status='processando'")


def document(row):
    obj = dict(row)
    obj['pages'] = json.loads(obj['pages'])
    obj['source_info'] = json.loads(obj.get('source_info') or '{}')
    return obj


def question(row):
    obj = dict(row)
    obj['options'] = json.loads(obj['options'])
    obj['visual_assets'] = json.loads(obj.get('visual_assets') or '{}')
    # Gabarito não é revelado antes de responder.
    obj.pop('answer')
    return obj

def draft(row):
    result = json.loads(row['data'])
    result.update(id=row['id'], document_id=row['document_id'], status=row['status'], question_id=row['question_id'])
    return result


def auto_import(doc_id):
    """Processa páginas em segundo plano; cada página é gravada atomicamente."""
    try:
        with connect() as db:
            row = db.execute('SELECT sha256,pages FROM documents WHERE id=?', (doc_id,)).fetchone()
            if not row: raise ValueError('Documento não encontrado.')
            source = DATA / 'pdfs' / (row['sha256'] + '.pdf')
            total = len(json.loads(row['pages']))
        duplicates, failed = set(), []
        for page in range(1, total + 1):
            with connect() as db:
                previous_page = db.execute('SELECT status FROM import_pages WHERE document_id=? AND page=?', (doc_id,page)).fetchone()
            if previous_page and previous_page['status'] == 'concluido':
                continue
            with tempfile.TemporaryDirectory(dir=DATA) as tmp:
                prefix = str(Path(tmp) / 'page')
                render = subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-singlefile','-scale-to','2000','-png',str(source),prefix],capture_output=True,timeout=30,check=False)
                if render.returncode: raise ValueError('Não foi possível renderizar uma página.')
                image_bytes = Path(prefix + '.png').read_bytes()
                items = None
                reason = 'Falha de configuração.'
                for attempt in range(2):
                    try:
                        items = settings_ai.extract_page(DATA, image_bytes)
                        break
                    except settings_ai.TutorError as exc:
                        reason = str(exc)
                    except ValueError:
                        reason = 'Confira a configuração da DeepSeek.'
                if items is None:
                    failed.append((page, reason))
                    with connect() as db:
                        db.execute('UPDATE import_jobs SET done=?,error=? WHERE document_id=?', (page, f'Falha na página {page}: {reason} O processamento continua.', doc_id))
                        db.execute("INSERT OR REPLACE INTO import_pages(document_id,page,status,error) VALUES(?,?,'falhou',?)", (doc_id,page,reason))
                    continue
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                page_duplicates = []
                existing = {int(r['number']) for r in db.execute('SELECT number FROM questions WHERE document_id=?', (doc_id,)) if str(r['number']).isdigit()}
                drafts = db.execute("SELECT id,data FROM drafts WHERE document_id=? AND status='em_revisao'", (doc_id,)).fetchall()
                for item in items:
                    number = int(item['numero'])
                    if number in existing:
                        duplicates.add(number)
                        page_duplicates.append(number)
                        continue
                    opts = [o['texto'].strip() for o in item['alternativas']]
                    assets = {'question': item['imagens'], 'options': [o.get('imagem') for o in item['alternativas']]}
                    candidates = [json.loads(r['data']) for r in drafts if str(json.loads(r['data']).get('number','')).isdigit() and int(json.loads(r['data'])['number']) == number]
                    context, context_page = item['contexto'].strip(), page
                    if not context and len(candidates) == 1 and candidates[0].get('context'):
                        fallback_page = candidates[0].get('context_page')
                        if type(fallback_page) is int and 1 <= fallback_page <= total:
                            context, context_page = candidates[0]['context'], fallback_page
                    prompt = item['enunciado'].strip()
                    if context_page == page and prompt.endswith(':') and re.match(r'^I\s*[.)]', context):
                        prompt, context, context_page = prompt + '\n' + context, '', None
                    subject = item['materia'].strip() or 'Não identificada'
                    if len(candidates) == 1 and candidates[0].get('subject') and candidates[0]['subject'] != 'Não identificada':
                        subject = candidates[0]['subject']
                    cur = db.execute('INSERT INTO questions(document_id,page,number,subject,prompt,options,answer,answer_source,created_at,context,context_page,review_method,visual_assets) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (doc_id,page,item['numero'],subject,prompt,json.dumps(opts,ensure_ascii=False),-1,'',now(),context,context_page,'ia_extracao',json.dumps(assets)))
                    existing.add(number)
                    for draft_row in drafts:
                        candidate = json.loads(draft_row['data']); raw = str(candidate.get('number',''))
                        if raw.isdigit() and int(raw) == number:
                            db.execute("UPDATE drafts SET status='publicada',question_id=? WHERE id=?", (cur.lastrowid,draft_row['id']))
                db.execute('UPDATE import_jobs SET done=? WHERE document_id=?', (page,doc_id))
                page_warning = 'Numeração repetida: ' + ', '.join(str(n) for n in sorted(page_duplicates)) if page_duplicates else ''
                db.execute("INSERT OR REPLACE INTO import_pages(document_id,page,status,error) VALUES(?,?,'concluido',?)", (doc_id,page,page_warning))
        with connect() as db:
            missing = db.execute("SELECT COUNT(*) FROM drafts WHERE document_id=? AND status='em_revisao'", (doc_id,)).fetchone()[0]
            count = db.execute('SELECT COUNT(*) FROM questions WHERE document_id=?', (doc_id,)).fetchone()[0]
            message = f'{missing} questões candidatas não foram extraídas pela IA.' if missing else ''
            page_warnings = [f"página {r['page']}: {r['error']}" for r in db.execute("SELECT page,error FROM import_pages WHERE document_id=? AND status='concluido' AND error != '' ORDER BY page", (doc_id,))]
            if page_warnings: message += ' ' + '; '.join(page_warnings) + '.'
            failed = [(r['page'],r['error']) for r in db.execute("SELECT page,error FROM import_pages WHERE document_id=? AND status='falhou' ORDER BY page", (doc_id,))]
            if failed: message += ' Falhas: ' + '; '.join(f'página {number}: {reason}' for number, reason in failed)
            if not count: message = 'Nenhuma questão foi extraída pela IA. ' + message
            status = 'falhou' if not count else ('parcial' if missing or page_warnings or failed else 'concluido')
            db.execute('UPDATE import_jobs SET status=?,error=? WHERE document_id=?', (status,message.strip(),doc_id))
            db.execute('UPDATE documents SET status=? WHERE id=?', (status,doc_id))
    except (ValueError, OSError, subprocess.SubprocessError, sqlite3.Error, settings_ai.TutorError):
        with connect() as db:
            db.execute("UPDATE import_jobs SET status='falhou',error='Não foi possível concluir a extração. Verifique a configuração de IA e tente novamente.' WHERE document_id=?", (doc_id,))


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
        if path == '/api/catalog':
            return self.send_json(200, list(catalog.CATALOG.values()))
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
            if path == '/api/simulations':
                db.execute('BEGIN IMMEDIATE')
                ids = [r['id'] for r in db.execute('SELECT id FROM simulations ORDER BY id DESC')]
                return self.send_json(200, [simulados.get(db, simulation_id) for simulation_id in ids])
            simulation = re.fullmatch(r'/api/simulations/(\d+)', path)
            if simulation:
                db.execute('BEGIN IMMEDIATE')
                try: result = simulados.get(db, int(simulation[1]))
                except ValueError: return self.send_json(404, {'error':'Simulado não encontrado.'})
                return self.send_json(200, result)
            excerpt = re.fullmatch(r'/api/questions/(\d+)/excerpt\.png', path)
            if excerpt:
                row = db.execute('SELECT q.number,q.page,d.sha256 FROM questions q JOIN documents d ON d.id=q.document_id WHERE q.id=?', (int(excerpt[1]),)).fetchone()
                if not row: return self.send_json(404, {'error':'Questão não encontrada.'})
                source = DATA / 'pdfs' / (row['sha256'] + '.pdf')
                try:
                    result = subprocess.run(['pdftotext','-f',str(row['page']),'-l',str(row['page']),'-bbox-layout',str(source),'-'], capture_output=True,timeout=20,check=False)
                    if result.returncode or len(result.stdout) > 8 * 1024 * 1024: raise ValueError('Página indisponível')
                    rect = question_region(result.stdout, row['number'])
                    if not rect: raise ValueError('Região não identificada')
                    with tempfile.TemporaryDirectory(dir=DATA) as tmp:
                        prefix = str(Path(tmp) / 'page')
                        cmd = ['pdftoppm','-f',str(row['page']),'-l',str(row['page']),'-singlefile','-scale-to','2000']
                        rendered = subprocess.run(cmd + ['-png',str(source),prefix],capture_output=True,timeout=20,check=False)
                        if rendered.returncode: raise ValueError('Falha ao renderizar')
                        raw = Path(prefix+'.png').read_bytes()
                        if raw[:8] != b'\x89PNG\r\n\x1a\n': raise ValueError('Imagem inválida')
                        width,height = struct.unpack('>II', raw[16:24])
                        x,y = int(rect[0]*width),int(rect[1]*height)
                        w,h = max(1,int(rect[2]*width)-x),max(1,int(rect[3]*height)-y)
                        result = subprocess.run(cmd + ['-x',str(x),'-y',str(y),'-W',str(w),'-H',str(h),'-png',str(source),prefix+'-crop'],capture_output=True,timeout=20,check=False)
                        if result.returncode: raise ValueError('Falha ao recortar')
                        content = Path(prefix+'-crop.png').read_bytes()
                    self.send_response(200); self.send_header('Content-Type','image/png'); self.send_header('Content-Length',str(len(content))); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(content); return
                except (ValueError, OSError, subprocess.SubprocessError):
                    return self.send_json(404, {'error':'Recorte não identificado nesta página.'})
            if path == '/api/import-jobs':
                return self.send_json(200, [dict(row) for row in db.execute('SELECT * FROM import_jobs ORDER BY document_id DESC')])
            job = re.fullmatch(r'/api/documents/(\d+)/import-job', path)
            if job:
                row = db.execute('SELECT * FROM import_jobs WHERE document_id=?', (int(job[1]),)).fetchone()
                return self.send_json(200, dict(row)) if row else self.send_json(404, {'error':'Processamento não encontrado.'})
            asset = re.fullmatch(r'/api/questions/(\d+)/assets/(question|option)/(\d+)\.png', path)
            if asset:
                row = db.execute('SELECT q.page,q.visual_assets,d.sha256 FROM questions q JOIN documents d ON d.id=q.document_id WHERE q.id=?', (int(asset[1]),)).fetchone()
                try:
                    if not row: raise ValueError('Questão inexistente')
                    boxes = json.loads(row['visual_assets']).get('question' if asset[2] == 'question' else 'options', [])
                    index = int(asset[3]); rect = boxes[index]
                    if rect is None: raise ValueError('Imagem inexistente')
                    settings_ai.validate_extraction({'questoes':[{'numero':'1','materia':'x','enunciado':'x','contexto':'','alternativas':[{'letra':'A','texto':'x','imagem':rect},{'letra':'B','texto':'x','imagem':None}],'imagens':[]}]})
                    with tempfile.TemporaryDirectory(dir=DATA) as tmp:
                        prefix = str(Path(tmp) / 'page'); source = DATA / 'pdfs' / (row['sha256'] + '.pdf')
                        result = subprocess.run(['pdftoppm','-f',str(row['page']),'-l',str(row['page']),'-singlefile','-scale-to','2000','-png',str(source),prefix],capture_output=True,timeout=30,check=False)
                        if result.returncode: raise ValueError('Falha ao renderizar imagem')
                        data = Path(prefix + '.png').read_bytes()
                        if data[:8] != b'\x89PNG\r\n\x1a\n': raise ValueError('Imagem inválida')
                        width,height = struct.unpack('>II',data[16:24])
                        x,y,w,h = padded_crop(rect, width, height)
                        result = subprocess.run(['pdftoppm','-f',str(row['page']),'-l',str(row['page']),'-singlefile','-scale-to','2000','-x',str(x),'-y',str(y),'-W',str(w),'-H',str(h),'-png',str(source),prefix+'-crop'],capture_output=True,timeout=30,check=False)
                        if result.returncode: raise ValueError('Falha ao recortar imagem')
                        data = Path(prefix+'-crop.png').read_bytes()
                    self.send_response(200); self.send_header('Content-Type','image/png'); self.send_header('Content-Length',str(len(data))); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(data); return
                except (ValueError, IndexError, TypeError, OSError, subprocess.SubprocessError, json.JSONDecodeError):
                    return self.send_json(404, {'error':'Imagem não disponível.'})
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
            match = re.fullmatch(r'/api/documents/(\d+)/(drafts|pdf|answer-keys)', path)
            if match:
                doc_id = int(match[1]); kind = match[2]
                row = db.execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone()
                if not row: return self.send_json(404, {'error': 'Documento não encontrado.'})
                if kind == 'drafts':
                    return self.send_json(200, [draft(r) for r in db.execute('SELECT * FROM drafts WHERE document_id=? ORDER BY id', (doc_id,))])
                if kind == 'answer-keys':
                    doc = document(row)
                    if doc['source_info'].get('kind') != 'gabarito':
                        return self.send_json(400, {'error': 'Este documento não foi importado como gabarito.'})
                    texts = [p['text'] for p in doc['pages']]
                    versions = answer_keys.selected_versions(texts, answer_keys.extract_versions(texts))
                    return self.send_json(200, {'versions': versions, 'matched': False})
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
            elif path in ('/api/questions', '/api/attempts', '/api/settings', '/api/tutor', '/api/catalog/import', '/api/simulations') or re.fullmatch(r'/api/simulations/\d+/(answer|finish)', path) or re.fullmatch(r'/api/drafts/\d+/publish', path) or re.fullmatch(r'/api/documents/\d+/(ocr|batch-review|batch-publish|resume-import)', path):
                if self.headers.get_content_type() != 'application/json':
                    raise ValueError('Use application/json.')
                data = json.loads(self.body(MAX_JSON))
                if not isinstance(data, dict):
                    raise ValueError('JSON deve ser um objeto.')
                if path == '/api/settings': self.send_json(200, settings_ai.update_settings(DATA, data))
                elif path == '/api/simulations': self.create_simulation(data)
                elif path.startswith('/api/simulations/'): self.update_simulation(int(path.split('/')[3]), path.rsplit('/', 1)[1], data)
                elif path == '/api/catalog/import': self.import_catalog(data)
                elif path == '/api/tutor': self.tutor(data)
                elif path == '/api/questions': self.add_question(data)
                elif path == '/api/attempts': self.add_attempt(data)
                elif path.startswith('/api/drafts/'): self.publish_draft(int(path.split('/')[3]), data)
                elif path.endswith('/batch-review'): self.batch_review(int(path.split('/')[3]), data)
                elif path.endswith('/batch-publish'): self.batch_publish(int(path.split('/')[3]), data)
                elif path.endswith('/resume-import'): self.resume_import(int(path.split('/')[3]), data)
                else: self.continue_ocr(int(path.split('/')[3]), data)
            else:
                self.send_json(404, {'error': 'Rota não encontrada.'})
        except settings_ai.TutorError as exc:
            self.send_json(502, {'error': str(exc)})
        except catalog.FetchError as exc:
            self.send_json(502, {'error': str(exc)})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.send_json(400, {'error': str(exc) or 'Dados inválidos.'})
        except (OSError, subprocess.SubprocessError, sqlite3.Error):
            self.send_json(500, {'error': 'Falha ao processar a solicitação.'})

    def create_simulation(self, data):
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            simulation_id = simulados.create(db, data)
            result = simulados.get(db, simulation_id)
        self.send_json(201, result)

    def update_simulation(self, simulation_id, action, data):
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if action == 'finish':
                if data: raise ValueError('Dados inesperados.')
                result = simulados.finish(db, simulation_id)
                accepted = True
            else:
                accepted = simulados.save_response(db, simulation_id, data)
                result = simulados.get(db, simulation_id)
        if not accepted: return self.send_json(409, {'error':'O simulado já foi finalizado ou o tempo terminou.', 'simulation':result})
        self.send_json(200, result)

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

    def resume_import(self, doc_id, data):
        if data: raise ValueError('Dados inesperados.')
        settings = settings_ai.get_settings(DATA)
        if settings['ai_provider'] != 'deepseek' or not settings['deepseek_key_configured'] or settings['deepseek_model'] != 'deepseek-flash':
            raise ValueError('Configure a DeepSeek antes de retomar.')
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM import_jobs WHERE document_id=?', (doc_id,)).fetchone()
            if not row or row['status'] not in ('parcial','falhou','interrompido'):
                raise ValueError('Esta importação não pode ser retomada.')
            db.execute("UPDATE import_jobs SET status='processando',error='' WHERE document_id=?", (doc_id,))
        threading.Thread(target=auto_import, args=(doc_id,), daemon=True).start()
        self.send_json(202, {'status':'processando'})

    def upload(self):
        if self.headers.get_content_type() != 'application/pdf':
            raise ValueError('Envie um PDF com Content-Type application/pdf.')
        content = self.body(MAX_PDF)
        if not content.startswith(b'%PDF-'):
            raise ValueError('Arquivo não possui assinatura PDF válida.')
        filename = Path(unquote(self.headers.get('X-Filename', 'documento.pdf')).replace('\\', '/')).name[:200]
        if not filename or any(ord(c) < 32 for c in filename):
            raise ValueError('Nome de arquivo inválido.')
        kind = self.headers.get('X-Document-Kind', 'prova')
        if kind not in ('prova', 'gabarito'):
            raise ValueError('Tipo de documento inválido.')
        automatic = self.headers.get('X-Auto-Extract', '').lower() == 'true' and kind == 'prova'
        if automatic:
            settings = settings_ai.get_settings(DATA)
            if settings['ai_provider'] != 'deepseek' or not settings['deepseek_key_configured'] or settings['deepseek_model'] != 'deepseek-flash':
                raise ValueError('Configure a chave e o modelo deepseek-flash em Configurações para importar com IA.')
        doc = self.import_pdf(content, filename, {'kind': kind} if kind == 'gabarito' else {}, enable_ocr=self.headers.get('X-Enable-OCR', '').lower() == 'true', reference=kind == 'gabarito')
        if automatic:
            with connect() as db:
                db.execute("INSERT INTO import_jobs(document_id,status,total) VALUES(?, 'processando', ?)", (doc['id'],len(doc['pages'])))
            threading.Thread(target=auto_import, args=(doc['id'],), daemon=True).start()
            doc['automatic_processing'] = True
        self.send_json(201, doc)

    def import_catalog(self, data):
        if set(data) != {'id'} or data['id'] not in catalog.CATALOG:
            raise ValueError('Selecione uma prova do catálogo.')
        item = catalog.CATALOG[data['id']]
        # Baixe ambos antes de registrar qualquer documento.
        exam = catalog.fetch_pdf(item['exam_url'], MAX_PDF)
        answer = catalog.fetch_pdf(item['answer_url'], MAX_PDF)
        source = {'catalog_id': item['id'], 'contest_url': item['contest_url'], 'retrieved_at': now(), 'version_match': 'pendente'}
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            exam_doc = self.import_pdf(exam, item['exam_name'], {**source, 'url': item['exam_url'], 'kind': 'prova'}, db=db)
            key_doc = self.import_pdf(answer, item['answer_name'], {**source, 'url': item['answer_url'], 'kind': 'gabarito'}, reference=True, db=db)
        self.send_json(201, {'exam': exam_doc, 'answer': key_doc, 'warning': item['description']})

    def import_pdf(self, content, filename, source_info, enable_ocr=False, reference=False, db=None):
        if len(content) > MAX_PDF or not content.startswith(b'%PDF-'):
            raise ValueError('Arquivo PDF inválido ou muito grande.')
        digest = hashlib.sha256(content).hexdigest()
        if source_info.get('catalog_id'):
            with (nullcontext(db) if db is not None else connect()) as conn:
                for existing in conn.execute('SELECT * FROM documents WHERE sha256=?', (digest,)):
                    old = document(existing)
                    if old['source_info'].get('catalog_id') == source_info['catalog_id'] and old['source_info'].get('kind') == source_info.get('kind'):
                        return old
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
            pages, bbox_xml = process_pages(src, pages, bbox_xml, enable_ocr=enable_ocr)
            try:
                candidates = extract_candidates(bbox_xml) if bbox_xml and not reference else []
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
        with (nullcontext(db) if db is not None else connect()) as conn:
            cur = conn.execute('INSERT INTO documents(filename,sha256,status,pages,created_at,source_info) VALUES(?,?,?,?,?,?)', (filename, digest, 'referencia' if reference else 'em_revisao', json.dumps(pages, ensure_ascii=False), now(), json.dumps(source_info, ensure_ascii=False)))
            conn.executemany('INSERT INTO drafts(document_id,data) VALUES(?,?)', [(cur.lastrowid, json.dumps(c, ensure_ascii=False)) for c in candidates])
            row = conn.execute('SELECT * FROM documents WHERE id=?', (cur.lastrowid,)).fetchone()
        return document(row)

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

    def batch_review(self, doc_id, data):
        if data.get('confirm') is not True or type(data.get('page')) is not int:
            raise ValueError('Confirme o envio e informe uma página.')
        page = data['page']
        with BATCH_REVIEW_LOCK:
            with connect() as db:
                doc = db.execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone()
                if not doc or not 1 <= page <= len(json.loads(doc['pages'])): raise ValueError('Página não encontrada.')
                rows = [r for r in db.execute("SELECT * FROM drafts WHERE document_id=? AND status='em_revisao'", (doc_id,)) if json.loads(r['data']).get('page') == page]
            if not rows: return self.send_json(200, {'count': 0})
            if len(rows) > 15: raise ValueError('Muitas questões nesta página; revise manualmente.')
            items = []
            for row in rows:
                item = json.loads(row['data'])
                items.append({'id': row['id'], 'numero': item.get('number'), 'materia': item.get('subject'), 'enunciado': item.get('prompt'), 'alternativas': item.get('options'), 'contexto': item.get('context'), 'imagem_associada': bool(illustration_for(doc['sha256'], item.get('number','')))})
            if len(json.dumps(items, ensure_ascii=False)) > 100000: raise ValueError('Lote muito grande para conferência.')
            with tempfile.TemporaryDirectory(dir=DATA) as tmp:
                prefix = str(Path(tmp) / 'page')
                source = DATA / 'pdfs' / (doc['sha256'] + '.pdf')
                result = subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-singlefile','-scale-to','2000','-png',str(source),prefix], capture_output=True, timeout=20, check=False)
                if result.returncode: raise ValueError('Não foi possível renderizar a página.')
                assessments = settings_ai.review_page(DATA, Path(prefix + '.png').read_bytes(), items)
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                for row in rows:
                    current = db.execute('SELECT data,status FROM drafts WHERE id=? AND document_id=?', (row['id'], doc_id)).fetchone()
                    if not current or current['status'] != 'em_revisao' or current['data'] != row['data']: continue
                    item = json.loads(current['data']); verdict = assessments[row['id']]
                    reasons = []
                    if not verdict['ok']: reasons.append(verdict['motivo'] or 'Divergência identificada pela IA.')
                    elif verdict['motivo'].strip(): reasons.append('Confira a observação da IA: ' + verdict['motivo'].strip())
                    if len(item.get('options', [])) != 5 or not item.get('prompt') or item.get('subject') in ('', None, 'Não identificada'): reasons.append('Estrutura ou matéria incompleta.')
                    if any(re.search(r'\bR\s+A\s+S\s+C\s+U\s+N\s+H\s+O\b', str(option), re.I) for option in item.get('options', [])):
                        reasons.append('Possível texto de rascunho anexado a uma alternativa.')
                    if item.get('context_page') and item['context_page'] != page: reasons.append('Texto de apoio em outra página exige conferência.')
                    if not item.get('context') and re.search(r'\b(tira|charge|figura|imagem|gráfico|gráﬁco|tabela|texto acima|texto a seguir)\b', item.get('prompt',''), re.I) and not illustration_for(doc['sha256'], item.get('number','')): reasons.append('Possível imagem ou texto de apoio não associado.')
                    item['batch_review'] = {'status': 'atencao' if reasons else 'sem_alerta', 'reasons': reasons, 'method': 'deepseek_visao', 'date': now()}
                    db.execute('UPDATE drafts SET data=? WHERE id=?', (json.dumps(item, ensure_ascii=False), row['id']))
            self.send_json(200, {'count': len(rows)})

    def batch_publish(self, doc_id, data):
        if data.get('confirm') is not True: raise ValueError('Confirme a publicação dos rascunhos conferidos automaticamente.')
        with BATCH_REVIEW_LOCK, connect() as db:
            db.execute('BEGIN IMMEDIATE')
            doc = db.execute('SELECT pages FROM documents WHERE id=?', (doc_id,)).fetchone()
            if not doc: raise ValueError('Documento não encontrado.')
            page_count = len(json.loads(doc['pages']))
            rows = db.execute("SELECT * FROM drafts WHERE document_id=? AND status='em_revisao'", (doc_id,)).fetchall()
            count = 0
            for row in rows:
                item = json.loads(row['data'])
                if item.get('batch_review', {}).get('status') != 'sem_alerta': continue
                opts = item.get('options'); page = item.get('page'); cp = item.get('context_page')
                if type(page) is not int or not 1 <= page <= page_count or (cp is not None and (type(cp) is not int or not 1 <= cp <= page_count)) or not isinstance(opts, list) or len(opts) != 5 or any(not isinstance(o,str) or not o.strip() or len(o)>5000 for o in opts) or any(not isinstance(item.get(k),str) or not item[k].strip() or len(item[k])>10000 for k in ('number','subject','prompt')) or not isinstance(item.get('context',''),str) or len(item.get('context',''))>30000:
                    continue
                cur = db.execute('INSERT INTO questions(document_id,page,number,subject,prompt,options,answer,answer_source,created_at,context,context_page,review_method) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (doc_id,page,item['number'],item['subject'],item['prompt'],json.dumps(opts,ensure_ascii=False),-1,'',now(),item.get('context',''),cp,'automatico'))
                db.execute("UPDATE drafts SET status='publicada',question_id=? WHERE id=?", (cur.lastrowid,row['id'])); count += 1
        self.send_json(200, {'published': count})

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
    bind_address = os.environ.get('ESTUDATJ_BIND', '127.0.0.1')
    if bind_address not in ('127.0.0.1', '0.0.0.0'):
        raise SystemExit('ESTUDATJ_BIND deve ser 127.0.0.1 ou 0.0.0.0.')
    ThreadingHTTPServer((bind_address, int(os.environ.get('ESTUDATJ_PORT', '8000'))), Handler).serve_forever()

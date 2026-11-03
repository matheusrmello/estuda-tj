"""Simulados locais com prazo persistente e correção apenas ao finalizar."""
import json
import random
from datetime import datetime, timedelta, timezone


def utcnow():
    return datetime.now(timezone.utc)


def create(db, data):
    if set(data) - {'quantidade', 'duracao_minutos', 'materia'}:
        raise ValueError('Configuração desconhecida.')
    count, minutes, subject = data.get('quantidade'), data.get('duracao_minutos'), data.get('materia', '')
    if type(count) is not int or not 1 <= count <= 200 or type(minutes) is not int or not 1 <= minutes <= 600 or not isinstance(subject, str) or len(subject) > 200:
        raise ValueError('Informe quantidade, duração e matéria válidas.')
    rows = db.execute('SELECT * FROM questions WHERE (? = ? OR subject = ?) ORDER BY id', (subject, '', subject)).fetchall()
    if count > len(rows):
        raise ValueError(f'Existem apenas {len(rows)} questões disponíveis para essa seleção.')
    selected = random.SystemRandom().sample(rows, count)
    snapshots = []
    for row in selected:
        item = dict(row)
        item['options'] = json.loads(item['options'])
        item['visual_assets'] = json.loads(item.get('visual_assets') or '{}')
        snapshots.append(item)
    start = utcnow()
    cur = db.execute('INSERT INTO simulations(created_at,deadline,status,subject,questions,responses) VALUES(?,?,?,?,?,?)',
                     (start.isoformat(), (start + timedelta(minutes=minutes)).isoformat(), 'em_andamento', subject, json.dumps(snapshots, ensure_ascii=False), '{}'))
    return cur.lastrowid


def _load(db, simulation_id):
    row = db.execute('SELECT * FROM simulations WHERE id=?', (simulation_id,)).fetchone()
    if not row:
        raise ValueError('Simulado não encontrado.')
    if row['status'] == 'em_andamento' and utcnow() >= datetime.fromisoformat(row['deadline']):
        db.execute("UPDATE simulations SET status='finalizado',finished_at=deadline WHERE id=?", (simulation_id,))
        row = db.execute('SELECT * FROM simulations WHERE id=?', (simulation_id,)).fetchone()
    return row


def serialize(row):
    obj = dict(row)
    items = json.loads(obj.pop('questions'))
    responses = json.loads(obj.pop('responses'))
    finished = obj['status'] == 'finalizado'
    result = {'acertos': 0, 'erros': 0, 'sem_gabarito': 0, 'nao_respondidas': 0}
    questions = []
    for item in items:
        selected = responses.get(str(item['id']))
        answer = item.pop('answer')
        source = item.pop('answer_source')
        item['selected'] = selected
        if finished:
            item['answer'] = answer if answer >= 0 else None
            item['answer_source'] = source
            item['correct'] = (selected == answer) if selected is not None and answer >= 0 else None
            if selected is None: result['nao_respondidas'] += 1
            elif answer < 0: result['sem_gabarito'] += 1
            elif selected == answer: result['acertos'] += 1
            else: result['erros'] += 1
        questions.append(item)
    obj['questions'] = questions
    obj['server_now'] = utcnow().isoformat()
    if finished: obj['result'] = result
    return obj


def get(db, simulation_id):
    return serialize(_load(db, simulation_id))


def save_response(db, simulation_id, data):
    if set(data) != {'question_id', 'selected'} or type(data['question_id']) is not int or (data['selected'] is not None and type(data['selected']) is not int):
        raise ValueError('Resposta inválida.')
    row = _load(db, simulation_id)
    if row['status'] != 'em_andamento':
        return False
    item = next((q for q in json.loads(row['questions']) if q['id'] == data['question_id']), None)
    selected = data['selected']
    if not item or (selected is not None and not 0 <= selected < len(item['options'])):
        raise ValueError('Questão ou alternativa inválida.')
    responses = json.loads(row['responses'])
    if selected is None: responses.pop(str(item['id']), None)
    else: responses[str(item['id'])] = selected
    db.execute('UPDATE simulations SET responses=? WHERE id=?', (json.dumps(responses), simulation_id))
    return True


def finish(db, simulation_id):
    row = _load(db, simulation_id)
    if row['status'] == 'em_andamento':
        db.execute("UPDATE simulations SET status='finalizado',finished_at=? WHERE id=?", (utcnow().isoformat(), simulation_id))
    return get(db, simulation_id)

import os
import logging
import secrets
import time
import math
import gemini
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from threading import Lock
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from flask import Flask, jsonify, request, session, g
from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, Numeric, String,
                        Text, create_engine, select, text, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, selectinload
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
app.config.update(SECRET_KEY=os.environ['SECRET_KEY'], MAX_CONTENT_LENGTH=256*1024,
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                  SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', 'true') == 'true',
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=12))
url = os.getenv('DATABASE_URL') or URL.create('mysql+pymysql', username=os.environ['MYSQL_USER'],
    password=os.environ['MYSQL_PASSWORD'], host='db', database=os.environ['MYSQL_DATABASE'],
    query={'charset': 'utf8mb4'})
engine = create_engine(url, pool_pre_ping=True, pool_size=4, max_overflow=2)
DB = sessionmaker(engine, expire_on_commit=False)
ph = PasswordHasher()
tz = ZoneInfo('America/Sao_Paulo')
def now(): return datetime.now(tz).replace(tzinfo=None)

class Base(DeclarativeBase): pass
class Account(Base):
    __tablename__ = 'account'
    id: Mapped[int] = mapped_column(primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(64))
class AISettings(Base):
    __tablename__ = 'ai_settings'
    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
class Exercise(Base):
    __tablename__ = 'exercises'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    muscle: Mapped[str] = mapped_column(String(60))
    custom: Mapped[bool] = mapped_column(Boolean, default=True)
class Routine(Base):
    __tablename__ = 'routines'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    goal: Mapped[str] = mapped_column(String(30))
    items: Mapped[list['RoutineItem']] = relationship(cascade='all, delete-orphan', order_by='RoutineItem.position')
class RoutineItem(Base):
    __tablename__ = 'routine_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    routine_id: Mapped[int] = mapped_column(ForeignKey('routines.id'))
    exercise_id: Mapped[int] = mapped_column(ForeignKey('exercises.id'))
    position: Mapped[int] = mapped_column(Integer)
    sets: Mapped[int] = mapped_column(Integer)
    reps: Mapped[int] = mapped_column(Integer)
    rest: Mapped[int] = mapped_column(Integer)
    exercise: Mapped[Exercise] = relationship()
class Workout(Base):
    __tablename__ = 'workouts'
    id: Mapped[int] = mapped_column(primary_key=True)
    routine_name: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default='')
    items: Mapped[list['WorkoutItem']] = relationship(cascade='all, delete-orphan', order_by='WorkoutItem.position')
class WorkoutItem(Base):
    __tablename__ = 'workout_items'
    id: Mapped[int] = mapped_column(primary_key=True)
    workout_id: Mapped[int] = mapped_column(ForeignKey('workouts.id'))
    exercise_id: Mapped[int | None] = mapped_column(ForeignKey('exercises.id'), nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(Integer)
    rest: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text, default='')
    sets: Mapped[list['WorkoutSet']] = relationship(cascade='all, delete-orphan', order_by='WorkoutSet.position')
class WorkoutSet(Base):
    __tablename__ = 'workout_sets'
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey('workout_items.id'))
    position: Mapped[int] = mapped_column(Integer)
    reps: Mapped[int] = mapped_column(Integer)
    load: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=0)
    done: Mapped[bool] = mapped_column(Boolean, default=False)

class Schedule(Base):
    __tablename__ = 'schedules'
    id: Mapped[int] = mapped_column(primary_key=True)
    routine_id: Mapped[int] = mapped_column(Integer)
    routine_name: Mapped[str] = mapped_column(String(100))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    workout_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class PushSubscription(Base):
    __tablename__ = 'push_subscriptions'
    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(500), unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    user_agent: Mapped[str] = mapped_column(String(255), default='')

CATALOG = {
 'Peito': ['Supino reto', 'Supino inclinado', 'Crucifixo'],
 'Costas': ['Puxada frontal', 'Remada baixa', 'Remada curvada'],
 'Pernas': ['Agachamento', 'Leg press', 'Cadeira extensora', 'Mesa flexora', 'Elevação de panturrilha'],
 'Ombros': ['Desenvolvimento', 'Elevação lateral'],
 'Braços': ['Rosca direta', 'Tríceps na polia'],
 'Abdômen': ['Abdominal', 'Prancha'],
 'Condicionamento': ['Bicicleta ergométrica', 'Caminhada na esteira']}
def initialize():
    Base.metadata.create_all(engine)
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE schedules ADD COLUMN notified_at DATETIME"))
            conn.commit()
    except Exception:
        pass
    with DB.begin() as db:
        if not db.scalar(select(Exercise.id).limit(1)):
            db.add_all(Exercise(name=n, muscle=m, custom=False) for m, names in CATALOG.items() for n in names)
for attempt in range(30):
    try:
        initialize(); break
    except Exception:
        if attempt == 29: raise
        time.sleep(2)

class InputError(Exception): pass
def string(value, label, limit=100):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise InputError(f'{label}: informe entre 1 e {limit} caracteres.')
    return value.strip()
def integer(value, label, lo, hi):
    if isinstance(value, bool): raise InputError(f'{label}: valor inválido.')
    try:
        n = int(value)
        if str(n) != str(value) or not lo <= n <= hi: raise ValueError()
        return n
    except (ValueError, TypeError): raise InputError(f'{label}: informe um inteiro de {lo} a {hi}.')
def load_value(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or not 0 <= n <= 9999 or n.as_tuple().exponent < -2: raise ValueError()
        return n
    except (ValueError, InvalidOperation): raise InputError('Carga: informe de 0 a 9999 kg, com até duas casas decimais.')
def data():
    d = request.get_json(silent=True)
    if not isinstance(d, dict): raise InputError('Formulário inválido.')
    return d
def notes(d):
    n = d.get('notes', '')
    if not isinstance(n, str) or len(n) > 2000: raise InputError('Observações: máximo de 2000 caracteres.')
    return n
GOALS = ['hipertrofia', 'força', 'condicionamento', 'emagrecimento']
def goal(d):
    if d.get('goal') not in GOALS: raise InputError('Escolha um objetivo válido.')
    return d['goal']
def found(db, cls, id):
    obj = db.get(cls, id)
    if obj is None: raise InputError('Registro não encontrado.')
    return obj

def authenticated(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with DB() as db:
            a = db.get(Account, 1)
            if not a or session.get('auth') != a.version: return jsonify(error='Entre para continuar.'), 401
        return fn(*args, **kwargs)
    return wrapped
@app.before_request
def csrf():
    if request.method in ('POST', 'PUT', 'DELETE'):
        token = session.get('csrf')
        if not token or not secrets.compare_digest(token, request.headers.get('X-CSRF-Token', '')):
            return jsonify(error='Atualize a página e tente novamente.'), 403
@app.errorhandler(InputError)
def invalid(e): return jsonify(error=str(e)), 400
@app.errorhandler(IntegrityError)
def conflict(e): return jsonify(error='Esse nome já existe ou o registro está em uso.'), 409
@app.errorhandler(413)
def oversized(e): return jsonify(error='Formulário muito grande.'), 413
@app.errorhandler(500)
def failed(e): return jsonify(error='Não foi possível concluir. Tente novamente.'), 500
# Timings include database statements and commit; no request bodies or SQL are logged.
@app.before_request
def timing_start():
    g.started = time.perf_counter()
    g.db_ms = 0.0
    g.db_queries = 0

@event.listens_for(engine, 'before_cursor_execute')
def sql_start(conn, cursor, statement, parameters, context, executemany):
    context.ritmo_started = time.perf_counter()

@event.listens_for(engine, 'after_cursor_execute')
def sql_end(conn, cursor, statement, parameters, context, executemany):
    from flask import has_request_context
    if has_request_context() and hasattr(g, 'db_ms'):
        g.db_ms += (time.perf_counter() - context.ritmo_started) * 1000
        g.db_queries += 1

original_commit = engine.dialect.do_commit
def timed_commit(connection):
    from flask import has_request_context
    start = time.perf_counter()
    try: return original_commit(connection)
    finally:
        if has_request_context() and hasattr(g, 'db_ms'):
            g.db_ms += (time.perf_counter() - start) * 1000
engine.dialect.do_commit = timed_commit

@app.after_request
def timing_finish(response):
    if hasattr(g, 'started'):
        total = (time.perf_counter() - g.started) * 1000
        response.headers['Server-Timing'] = f'api;dur={total:.2f}, db;dur={g.db_ms:.2f}'
        app.logger.info('request route=%s method=%s status=%s api_ms=%.2f db_ms=%.2f queries=%s',
                        request.url_rule.rule if request.url_rule else 'unknown', request.method,
                        response.status_code, total, g.db_ms, g.db_queries)
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/api/schedules')
@authenticated
def schedules():
    try:
        start = datetime.strptime(request.args.get('month', ''), '%Y-%m')
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    except ValueError: raise InputError('Mês inválido.')
    with DB() as db:
        entries = db.scalars(select(Schedule).where(Schedule.scheduled_at >= start,
                            Schedule.scheduled_at < end).order_by(Schedule.scheduled_at))
        return jsonify([dict(id=e.id, routine_id=e.routine_id, routine_name=e.routine_name,
                       scheduled_at=e.scheduled_at.replace(tzinfo=tz).isoformat(),
                       workout_id=e.workout_id, status=('concluído' if e.workout_id and
                       (w := db.get(Workout, e.workout_id)) and w.finished_at else
                       'em andamento' if e.workout_id and db.get(Workout, e.workout_id) else 'agendado'))
                       for e in entries])

schedule_lock = Lock()

@app.post('/api/schedules')
@authenticated
def schedule_create():
    d = data()
    try:
        stamp = datetime.strptime(d.get('scheduled_at', ''), '%Y-%m-%dT%H:%M')
    except (ValueError, TypeError): raise InputError('Informe uma data e horário válidos.')
    with schedule_lock, DB.begin() as db:
        r = found(db, Routine, integer(d.get('routine_id'), 'Rotina', 1, 1000000))
        if db.scalar(select(Schedule.id).where(Schedule.routine_id == r.id, Schedule.scheduled_at == stamp)):
            raise InputError('Esta rotina já está agendada neste horário.')
        entry = Schedule(routine_id=r.id, routine_name=r.name, scheduled_at=stamp)
        db.add(entry); db.flush()
        return jsonify(id=entry.id)

@app.delete('/api/schedules/<int:id>')
@authenticated
def schedule_delete(id):
    with DB.begin() as db:
        db.delete(found(db, Schedule, id))
    return jsonify(ok=True)

@app.get('/api/health')
def health():
    with engine.connect() as c: c.execute(text('SELECT 1'))
    return jsonify(status='ok')
@app.get('/api/auth')
def auth():
    if 'csrf' not in session: session['csrf'] = secrets.token_hex(32)
    with DB() as db:
        a = db.get(Account, 1)
        return jsonify(csrf=session['csrf'], authenticated=bool(a and session.get('auth') == a.version), configured=bool(a))
# Um único worker atende este usuário; o limite é compartilhado pelas threads.
login_lock = Lock()
failures = []
@app.post('/api/login')
def login():
    password = data().get('password')
    if not isinstance(password, str) or len(password) > 256: raise InputError('Senha inválida.')
    with login_lock:
        stamp = time.monotonic()
        failures[:] = [t for t in failures if stamp - t < 300]
        if len(failures) >= 10: return jsonify(error='Muitas tentativas. Aguarde cinco minutos.'), 429
        with DB.begin() as db:
            a = db.get(Account, 1)
            if not a: return jsonify(error='Configure a senha inicial no servidor. Consulte o README.'), 503
            try: ph.verify(a.password_hash, password)
            except VerificationError:
                failures.append(stamp)
                return jsonify(error='Senha incorreta.'), 401
            if ph.check_needs_rehash(a.password_hash): a.password_hash = ph.hash(password)
            session.clear(); session.permanent = True
            session.update(auth=a.version, csrf=secrets.token_hex(32))
            failures.clear()
    return jsonify(ok=True, csrf=session['csrf'])
@app.post('/api/logout')
def logout(): session.clear(); return jsonify(ok=True)

catalog_lock = Lock()

def ex_dict(e): return dict(id=e.id, name=e.name, muscle=e.muscle, custom=e.custom)
@app.get('/api/exercises')
@authenticated
def exercises():
    with DB() as db: return jsonify([ex_dict(e) for e in db.scalars(select(Exercise).order_by(Exercise.muscle, Exercise.name))])
@app.route('/api/exercises', methods=['POST'])
@app.route('/api/exercises/<int:id>', methods=['PUT', 'DELETE'])
@authenticated
def exercise_edit(id=None):
    with catalog_lock, DB.begin() as db:
        e = found(db, Exercise, id) if id else Exercise(custom=True)
        if request.method == 'DELETE' and not e.custom: raise InputError('O catálogo inicial pode ser editado, mas não excluído.')
        if request.method == 'DELETE':
            if db.scalar(select(RoutineItem.id).where(RoutineItem.exercise_id == id).limit(1)):
                raise InputError('Remova o exercício das rotinas antes de excluir.')
            for w in db.scalars(select(WorkoutItem).where(WorkoutItem.exercise_id == id)): w.exercise_id = None
            db.delete(e); return jsonify(ok=True)
        d=data(); e.name=string(d.get('name'), 'Nome'); e.muscle=string(d.get('muscle'), 'Grupo muscular', 60)
        if any(other.id != e.id and gemini.normalize(other.name) == gemini.normalize(e.name) for other in db.scalars(select(Exercise))):
            raise InputError('Um exercício equivalente já existe no catálogo. Use o existente.')
        db.add(e); db.flush(); return jsonify(ex_dict(e))

def routine_dict(r):
    return dict(id=r.id, name=r.name, goal=r.goal, items=[dict(exercise_id=i.exercise_id,
        name=i.exercise.name, sets=i.sets, reps=i.reps, rest=i.rest) for i in r.items])
def set_routine(db, r, d):
    r.name=string(d.get('name'), 'Nome'); r.goal=goal(d)
    items=d.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 25: raise InputError('Inclua de 1 a 25 exercícios.')
    r.items.clear()
    for pos,i in enumerate(items):
        if not isinstance(i, dict): raise InputError('Exercício inválido.')
        ex=found(db, Exercise, integer(i.get('exercise_id'), 'Exercício', 1, 1000000))
        r.items.append(RoutineItem(exercise=ex, position=pos, sets=integer(i.get('sets'), 'Séries',1,20),
             reps=integer(i.get('reps'),'Repetições',1,1000), rest=integer(i.get('rest'),'Descanso',0,600)))
@app.get('/api/routines')
@authenticated
def routines():
    with DB() as db: return jsonify([routine_dict(r) for r in db.scalars(select(Routine).options(selectinload(Routine.items).selectinload(RoutineItem.exercise)).order_by(Routine.id))])
@app.route('/api/routines', methods=['POST'])
@app.route('/api/routines/<int:id>', methods=['PUT','DELETE'])
@authenticated
def routine_edit(id=None):
    with DB.begin() as db:
        r=found(db,Routine,id) if id else Routine()
        if request.method == 'DELETE': db.delete(r); return jsonify(ok=True)
        set_routine(db,r,data()); db.add(r); db.flush(); return jsonify(routine_dict(r))
@app.post('/api/suggest')
@authenticated
def suggest():
    d=data(); g=goal(d); days=integer(d.get('days'),'Dias',1,6); minutes=integer(d.get('minutes'),'Tempo',15,120)
    templates=[['Agachamento','Supino reto','Remada baixa','Mesa flexora','Desenvolvimento','Abdominal'],
               ['Leg press','Supino inclinado','Puxada frontal','Elevação de panturrilha','Rosca direta','Tríceps na polia']]
    if days >= 4:
        templates=[['Supino reto','Remada baixa','Desenvolvimento','Rosca direta','Tríceps na polia'],
                   ['Agachamento','Mesa flexora','Leg press','Elevação de panturrilha','Abdominal']]
    sets,reps,rest=(4,5,150) if g=='força' else (3,10,90) if g=='hipertrofia' else (2,15,45)
    count=max(2,min(6, int(minutes // (sets*(1+rest/60)+1))))
    with DB() as db:
        catalog=list(db.scalars(select(Exercise).order_by(Exercise.id)))
        by_name={e.name:e for e in catalog}
        seeds=[n for names in CATALOG.values() for n in names]
        for e in catalog:
            if not e.custom and 1 <= e.id <= len(seeds): by_name[seeds[e.id-1]]=e
        plans=[]
        for day in range(days):
            names=templates[day%2][:count]
            if g in ('condicionamento','emagrecimento') and count >= 3: names=names[:-1]+['Bicicleta ergométrica']
            plans.append(dict(name=f'Treino {chr(65+day)} — {g}',goal=g,items=[dict(exercise_id=by_name[n].id,
              name=by_name[n].name,sets=sets,reps=reps,rest=rest) for n in names if n in by_name]))
    return jsonify(routines=plans, note='Modelo inicial editável. Séries e repetições são contagens; para bicicleta/esteira, use as observações para registrar duração. Ajuste os exercícios à sua experiência e ao tempo real da sessão.')

@app.errorhandler(gemini.GeminiError)
def gemini_failed(e): return jsonify(error=str(e)), e.status

def ai_enabled(db):
    setting = db.get(AISettings, 1)
    return bool(setting and setting.enabled)

@app.route('/api/ai/settings', methods=['GET', 'PUT'])
@authenticated
def ai_settings():
    with DB.begin() as db:
        if request.method == 'PUT':
            enabled = data().get('enabled')
            if not isinstance(enabled, bool): raise InputError('Escolha habilitar ou desativar a integração.')
            setting = db.get(AISettings, 1)
            if not setting:
                setting = AISettings(id=1); db.add(setting)
            setting.enabled = enabled
            db.flush()
        return jsonify(configured=gemini.configured(), enabled=ai_enabled(db), model=gemini.MODEL)

def ai_profile(d):
    if d.get('consent') is not True: raise InputError('Autorize o envio dos campos informados à Google antes de gerar.')
    experience = d.get('experience')
    if experience not in ('iniciante', 'intermediário', 'avançado'): raise InputError('Escolha a experiência.')
    profile = dict(goal=goal(d), experience=experience, days=integer(d.get('days'),'Dias',1,6),
                   minutes=integer(d.get('minutes'),'Tempo',15,120), equipment=string(d.get('equipment'),'Equipamentos',500))
    limitations = d.get('limitations', '')
    if not isinstance(limitations, str) or len(limitations) > 500: raise InputError('Limitações: máximo de 500 caracteres.')
    profile['limitations'] = limitations.strip()
    for name, label, lo, hi in [('weight','Peso',20,500), ('height','Altura',80,250)]:
        value = d.get(name)
        if value is None or value == '': continue
        if isinstance(value, bool) or not isinstance(value, (float,int)) or not math.isfinite(value) or not lo <= value <= hi:
            raise InputError(f'{label}: informe de {lo} a {hi}, ou deixe vazio.')
        profile[name] = value
    return profile

def validate_ai_routine(d, g):
    if not isinstance(d, dict) or set(d) != {'name', 'items'}: raise InputError('Rascunho inválido: campos não permitidos.')
    name = string(d.get('name'), 'Nome da rotina')
    if not gemini.safe_name(name): raise InputError('Rascunho recusado: instrução médica, de carga ou texto não permitido.')
    items = d.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 12: raise InputError('Rascunho deve ter de 1 a 12 exercícios.')
    result = dict(name=name, goal=g, items=[])
    seen = set()
    for i in items:
        if not isinstance(i, dict) or set(i) != {'name','muscle','sets','reps','rest'}:
            raise InputError('Exercício inválido: não são aceitos campos de carga ou instruções clínicas.')
        name = string(i.get('name'), 'Nome do exercício')
        key = gemini.normalize(name)
        if not key or not gemini.safe_name(name): raise InputError('Nome de exercício não permitido.')
        if key in seen: raise InputError('O rascunho repete um exercício equivalente. Revise antes de salvar.')
        seen.add(key)
        if i.get('muscle') not in gemini.SCHEMA['properties']['routines']['items']['properties']['items']['items']['properties']['muscle']['enum']:
            raise InputError('Grupo muscular não permitido no rascunho.')
        values={}
        for field, lo, hi in [('sets',1,6), ('reps',1,30), ('rest',0,300)]:
            if type(i.get(field)) is not int: raise InputError('Contagens do rascunho devem ser inteiros.')
            values[field] = integer(i[field], field, lo, hi)
        result['items'].append(dict(name=name, muscle=i['muscle'], **values))
    return result

# Um usuário/worker. O limite local protege contra cliques repetidos; as cotas reais são da Google.
ai_lock = Lock()
ai_last_request = 0
@app.post('/api/ai/suggest')
@authenticated
def ai_suggest():
    global ai_last_request
    profile = ai_profile(data())
    if not gemini.configured(): raise gemini.GeminiError('Gemini não configurado para projeto gratuito. Use as sugestões locais ou crie rotinas manualmente.')
    with DB() as db:
        if not ai_enabled(db): raise InputError('Integração desativada. Habilite-a antes de enviar dados.')
    if not ai_lock.acquire(blocking=False): raise gemini.GeminiError('Uma sugestão já está sendo gerada. Aguarde.',429)
    try:
        stamp = time.monotonic()
        if stamp - ai_last_request < 60: raise gemini.GeminiError('Aguarde um minuto entre solicitações ao Gemini. O modo manual continua disponível.',429)
        ai_last_request = stamp
        raw = gemini.generate(profile)
        try:
            if not isinstance(raw,dict) or set(raw) != {'routines'} or not isinstance(raw['routines'],list) or len(raw['routines']) != profile['days']:
                raise InputError('Quantidade de rotinas inválida.')
            plans = [validate_ai_routine(r,profile['goal']) for r in raw['routines']]
        except InputError:
            raise gemini.GeminiError('A resposta do Gemini não passou na validação de rascunho. Nada foi salvo. Use o modo manual ou tente mais tarde.',502) from None
        with DB() as db:
            if not ai_enabled(db) or not gemini.configured(): raise InputError('Integração desativada durante a geração. O resultado foi descartado.')
            existing = {gemini.normalize(e.name): e for e in db.scalars(select(Exercise).order_by(Exercise.id))}
            for r in plans:
                for i in r['items']:
                    e = existing.get(gemini.normalize(i['name']))
                    i['existing_id'] = e.id if e else None
                    i['existing_name'] = e.name if e else None
        return jsonify(routines=plans, note='Rascunho de IA: revise a adequação dos exercícios antes de salvar. Não inclui cargas, diagnóstico ou tratamento.')
    finally: ai_lock.release()

@app.post('/api/ai/import')
@authenticated
def ai_import():
    d = data()
    if d.get('reviewed') is not True: raise InputError('Revise e confirme o rascunho antes de salvar.')
    r = validate_ai_routine(d.get('routine'),goal(d))
    # Gravação ocorre exclusivamente nesta ação humana, em uma transação atômica.
    with catalog_lock, DB.begin() as db:
        existing = {gemini.normalize(e.name): e for e in db.scalars(select(Exercise).order_by(Exercise.id))}
        items=[]
        for i in r['items']:
            key=gemini.normalize(i['name'])
            e=existing.get(key)
            if not e:
                e=Exercise(name=i['name'],muscle=i['muscle'],custom=True)
                db.add(e);db.flush();existing[key]=e
            items.append(dict(exercise_id=e.id,sets=i['sets'],reps=i['reps'],rest=i['rest']))
        routine=Routine()
        set_routine(db,routine,dict(name=r['name'],goal=r['goal'],items=items))
        db.add(routine);db.flush()
        return jsonify(routine_dict(routine))

def workout_dict(w):
    return dict(id=w.id,routine_name=w.routine_name,started_at=w.started_at.replace(tzinfo=tz).isoformat(),
      finished_at=w.finished_at.replace(tzinfo=tz).isoformat() if w.finished_at else None,notes=w.notes,
      items=[dict(id=i.id,exercise_id=i.exercise_id,name=i.name,rest=i.rest,notes=i.notes,
        sets=[dict(id=s.id,reps=s.reps,load=float(s.load),done=s.done) for s in i.sets]) for i in w.items])
@app.get('/api/workouts')
@authenticated
def workouts():
    month=request.args.get('month','')
    try: start=datetime.strptime(month,'%Y-%m'); end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
    except ValueError: raise InputError('Mês inválido.')
    with DB() as db:
        ws=db.scalars(select(Workout).options(selectinload(Workout.items).selectinload(WorkoutItem.sets)).where(Workout.finished_at.is_not(None),Workout.started_at>=start,Workout.started_at<end).order_by(Workout.started_at.desc()))
        return jsonify([workout_dict(w) for w in ws])
@app.get('/api/workouts/active')
@authenticated
def active():
    with DB() as db:
        w=db.scalar(select(Workout).options(selectinload(Workout.items).selectinload(WorkoutItem.sets)).where(Workout.finished_at.is_(None)).order_by(Workout.id.desc()))
        return jsonify(workout_dict(w) if w else None)
workout_lock = Lock()

@app.post('/api/workouts')
@authenticated
def start_workout():
    with workout_lock, DB.begin() as db:
        if db.scalar(select(Workout.id).where(Workout.finished_at.is_(None)).limit(1)):
            raise InputError('Já existe um treino em andamento. Retome ou descarte esse treino.')
        d=data()
        r=found(db,Routine,integer(d.get('routine_id'),'Rotina',1,1000000))
        entry = found(db, Schedule, integer(d['schedule_id'], 'Agendamento', 1, 1000000)) if d.get('schedule_id') else None
        if entry and (entry.routine_id != r.id or entry.workout_id): raise InputError('Agendamento já iniciado ou rotina inválida.')
        w=Workout(routine_name=r.name,started_at=now(),notes='')
        for pos,i in enumerate(r.items):
            w.items.append(WorkoutItem(exercise_id=i.exercise_id,name=i.exercise.name,position=pos,rest=i.rest,notes='',
              sets=[WorkoutSet(position=n,reps=i.reps,load=0,done=False) for n in range(i.sets)]))
        db.add(w);db.flush()
        if entry: entry.workout_id = w.id
        return jsonify(workout_dict(w))
@app.route('/api/workouts/<int:id>',methods=['GET','PUT','DELETE'])
@authenticated
def workout_edit(id):
    with workout_lock, DB.begin() as db:
        w=db.scalar(select(Workout).options(selectinload(Workout.items).selectinload(WorkoutItem.sets)).where(Workout.id==id))
        if w is None: raise InputError('Registro não encontrado.')
        if request.method=='GET': return jsonify(workout_dict(w))
        if request.method=='DELETE':
            for entry in db.scalars(select(Schedule).where(Schedule.workout_id == w.id)): entry.workout_id = None
            db.delete(w); return jsonify(ok=True)
        if w.finished_at: raise InputError('Treino já finalizado.')
        d=data();w.notes=notes(d)
        items=d.get('items')
        if not isinstance(items,list) or len(items)!=len(w.items): raise InputError('Exercícios inválidos.')
        for saved,edit in zip(w.items,items):
            if not isinstance(edit,dict) or edit.get('id')!=saved.id: raise InputError('Exercício inválido.')
            saved.notes=notes(edit)
            ss=edit.get('sets')
            if not isinstance(ss,list) or len(ss)!=len(saved.sets): raise InputError('Séries inválidas.')
            for s,v in zip(saved.sets,ss):
                if not isinstance(v,dict) or v.get('id')!=s.id or not isinstance(v.get('done'),bool): raise InputError('Série inválida.')
                s.reps=integer(v.get('reps'),'Repetições',0,1000);s.load=load_value(v.get('load'));s.done=v['done']
                if s.done and s.reps==0: raise InputError('Série concluída precisa ter repetições.')
        if d.get('finish'):
            if not any(s.done for i in w.items for s in i.sets): raise InputError('Conclua pelo menos uma série antes de finalizar.')
            w.finished_at=now()
        db.flush();return jsonify(workout_dict(w))
@app.get('/api/history/<int:id>')
@authenticated
def history(id):
    with DB() as db:
        rows=db.execute(select(Workout.started_at,WorkoutItem.name,WorkoutSet.reps,WorkoutSet.load)
          .join(WorkoutItem,WorkoutItem.workout_id==Workout.id).join(WorkoutSet,WorkoutSet.item_id==WorkoutItem.id)
          .where(WorkoutItem.exercise_id==id,Workout.finished_at.is_not(None),WorkoutSet.done.is_(True))
          .order_by(Workout.started_at,WorkoutSet.position)).all()
        return jsonify([dict(date=r[0].replace(tzinfo=tz).isoformat(),name=r[1],reps=r[2],load=float(r[3])) for r in rows])

@app.get('/api/history')
@authenticated
def history_batch():
    values = request.args.get('ids', '').split(',')
    ids = list({integer(v, 'Exercício', 1, 1000000) for v in values if v})
    if len(ids) > 25: raise InputError('Máximo de 25 exercícios.')
    with DB() as db:
        rows=db.execute(select(WorkoutItem.exercise_id,Workout.started_at,WorkoutItem.name,WorkoutSet.reps,WorkoutSet.load)
          .join(WorkoutItem,WorkoutItem.workout_id==Workout.id).join(WorkoutSet,WorkoutSet.item_id==WorkoutItem.id)
          .where(WorkoutItem.exercise_id.in_(ids),Workout.finished_at.is_not(None),WorkoutSet.done.is_(True))
          .order_by(Workout.started_at,WorkoutSet.position)).all()
        result={id:[] for id in ids}
        for r in rows: result[r[0]].append(dict(date=r[1].replace(tzinfo=tz).isoformat(),name=r[2],reps=r[3],load=float(r[4])))
        return jsonify(result)

VAPID_PRIVATE_KEY_PATH = os.path.expanduser('~/.local/share/ritmo/vapid_private.pem')
def get_vapid_public_key():
    if not os.path.exists(VAPID_PRIVATE_KEY_PATH): return ''
    try:
        from py_vapid import Vapid
        import base64
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        v = Vapid.from_file(VAPID_PRIVATE_KEY_PATH)
        raw_pub = v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        return base64.urlsafe_b64encode(raw_pub).decode().rstrip('=')
    except Exception as e:
        app.logger.warning("Error loading VAPID key: %s", e)
        return ''

VAPID_PUBLIC_KEY = get_vapid_public_key()

@app.get('/api/push/public_key')
def push_public_key():
    return jsonify(publicKey=VAPID_PUBLIC_KEY)

@app.post('/api/push/subscribe')
@authenticated
def push_subscribe():
    d = data()
    endpoint = (d.get('endpoint') or '').strip()
    keys = d.get('keys') or {}
    p256dh = keys.get('p256dh', '').strip()
    auth = keys.get('auth', '').strip()
    if not endpoint or not p256dh or not auth:
        raise InputError('Inscrição push inválida.')
    with DB.begin() as db:
        existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
        if existing:
            existing.p256dh = p256dh
            existing.auth = auth
            existing.user_agent = request.headers.get('User-Agent', '')[:255]
        else:
            db.add(PushSubscription(endpoint=endpoint, p256dh=p256dh, auth=auth,
                                    user_agent=request.headers.get('User-Agent', '')[:255]))
    return jsonify(success=True)

@app.post('/api/push/unsubscribe')
@authenticated
def push_unsubscribe():
    d = data()
    endpoint = (d.get('endpoint') or '').strip()
    if endpoint:
        with DB.begin() as db:
            sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
            if sub: db.delete(sub)
    return jsonify(success=True)

@app.post('/api/push/test')
@authenticated
def push_test():
    sent = 0
    subs_count = 0
    with DB.begin() as db:
        subs = list(db.scalars(select(PushSubscription)))
        subs_count = len(subs)
        if subs:
            try:
                from pywebpush import webpush, WebPushException
                for s in subs:
                    try:
                        webpush(
                            subscription_info={
                                "endpoint": s.endpoint,
                                "keys": {"p256dh": s.p256dh, "auth": s.auth}
                            },
                            data=json.dumps({
                                "title": "Ritmo · Notificações Ativas",
                                "body": "Suas notificações de treino estão funcionando perfeitamente!",
                                "tag": "ritmo-test",
                                "url": "/#inicio"
                            }),
                            vapid_private_key=VAPID_PRIVATE_KEY_PATH,
                            vapid_claims={"sub": "mailto:ritmo@localhost"},
                            timeout=10
                        )
                        sent += 1
                    except WebPushException as ex:
                        if ex.response and ex.response.status_code in (404, 410):
                            db.delete(s)
                        app.logger.warning("Push test error: %s", ex)
                    except Exception as e:
                        app.logger.warning("Push error: %s", e)
            except Exception as e:
                app.logger.warning("WebPush module error: %s", e)
    return jsonify(sent=sent, total=subs_count)


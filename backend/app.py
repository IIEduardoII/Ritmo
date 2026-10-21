import os
import logging
import secrets
import time
import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request, session, g, send_from_directory
from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String,
                        Text, create_engine, select, text, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, selectinload
from sqlalchemy.engine import Engine, URL
from sqlalchemy.exc import IntegrityError

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "")
VERSION = "1.1.0"

# Secret key and session setup
SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024, # 16 MB max upload for high-res photos
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', 'false') == 'true',
    PERMANENT_SESSION_LIFETIME=timedelta(days=365)
)

# SQLite database setup with WAL mode and high-resilience pragmas
DEFAULT_DB_PATH = os.path.expanduser('~/.local/share/ritmo/ritmo.sqlite3')
if IS_TERMUX:
    DEFAULT_DB_PATH = '/data/data/com.termux/files/home/.local/share/ritmo/ritmo.sqlite3'

db_url = os.getenv('DATABASE_URL')
if not db_url:
    os.makedirs(os.path.dirname(DEFAULT_DB_PATH), exist_ok=True)
    db_url = f"sqlite:///{DEFAULT_DB_PATH}"

engine = create_engine(db_url, pool_pre_ping=True)

# Static photo upload directory
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'evolution')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass

DB = sessionmaker(engine, expire_on_commit=False)
tz = ZoneInfo('America/Sao_Paulo')

def now():
    return datetime.now(tz).replace(tzinfo=None)

def today_date():
    return datetime.now(tz).date()

# ---------------------------------------------------------------------------
# Database Schema (Relational Models - Ritmo v1.1)
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), default='Atleta')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class BodyMetric(Base):
    __tablename__ = 'body_metrics'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, default=1)
    weight: Mapped[float] = mapped_column(Numeric(5, 2))
    notes: Mapped[str] = mapped_column(Text, default='')
    recorded_at: Mapped[str] = mapped_column(String(10), unique=True, index=True) # YYYY-MM-DD
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class EvolutionPhoto(Base):
    __tablename__ = 'evolution_photos'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, default=1)
    metric_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    photo_path: Mapped[str] = mapped_column(String(255))
    angle: Mapped[str] = mapped_column(String(20), default='frontal') # frontal, costas, lateral, outro
    taken_at: Mapped[str] = mapped_column(String(10), index=True) # YYYY-MM-DD
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Exercise(Base):
    __tablename__ = 'exercises'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    muscle_group: Mapped[str] = mapped_column(String(50), index=True)
    equipment: Mapped[str] = mapped_column(String(100), default='')
    notes: Mapped[str] = mapped_column(Text, default='')
    custom: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    # Coluna legada da v1.0 (NOT NULL no banco migrado). Mantida em sincronia com muscle_group.
    legacy_muscle: Mapped[str] = mapped_column('muscle', String(60), default='')

class Routine(Base):
    __tablename__ = 'routines'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(100))
    target_muscle_groups: Mapped[str] = mapped_column(String(255), default='') # ex: 'peito,triceps'
    day_of_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    # Coluna legada da v1.0 (NOT NULL no banco migrado). O conceito de "foco" não é mais usado.
    legacy_goal: Mapped[str] = mapped_column('goal', String(30), default='')
    items: Mapped[list['RoutineItem']] = relationship(cascade='all, delete-orphan', order_by='RoutineItem.position')

class RoutineItem(Base):
    __tablename__ = 'routine_items'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    routine_id: Mapped[int] = mapped_column(ForeignKey('routines.id', ondelete='CASCADE'), index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey('exercises.id', ondelete='CASCADE'), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    sets: Mapped[int] = mapped_column(Integer, default=3)
    reps: Mapped[int] = mapped_column(Integer, default=10)
    rest: Mapped[int] = mapped_column(Integer, default=90)
    target_reps: Mapped[str] = mapped_column(String(20), default='8-12')
    exercise: Mapped[Exercise] = relationship()

class Workout(Base):
    __tablename__ = 'workouts'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, default=1)
    routine_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    routine_name: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default='')
    session_date: Mapped[str] = mapped_column(String(10), index=True) # YYYY-MM-DD
    items: Mapped[list['WorkoutItem']] = relationship(cascade='all, delete-orphan', order_by='WorkoutItem.position')

class WorkoutItem(Base):
    __tablename__ = 'workout_items'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workout_id: Mapped[int] = mapped_column(ForeignKey('workouts.id', ondelete='CASCADE'), index=True)
    exercise_id: Mapped[int | None] = mapped_column(ForeignKey('exercises.id'), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(Integer, default=0)
    rest: Mapped[int] = mapped_column(Integer, default=90)
    notes: Mapped[str] = mapped_column(Text, default='')
    sets: Mapped[list['WorkoutSet']] = relationship(cascade='all, delete-orphan', order_by='WorkoutSet.position')

class WorkoutSet(Base):
    __tablename__ = 'workout_sets'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(ForeignKey('workout_items.id', ondelete='CASCADE'), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    load: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=0)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    rpe: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Schedule(Base):
    __tablename__ = 'schedules'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, default=1)
    routine_id: Mapped[int] = mapped_column(Integer, index=True)
    routine_name: Mapped[str] = mapped_column(String(100))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    workout_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class PushSubscription(Base):
    __tablename__ = 'push_subscriptions'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    endpoint: Mapped[str] = mapped_column(String(500), unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    user_agent: Mapped[str] = mapped_column(String(255), default='')

# Standard Anatomical Muscle Groups (Taxonomia v1.1)
MUSCLE_GROUPS = [
    'peito', 'costas', 'quadriceps', 'posterior',
    'ombros', 'biceps', 'triceps', 'abdomen', 'panturrilha', 'outro'
]

CATALOG = {
    'peito': ['Supino reto com barra', 'Supino inclinado com halteres', 'Crucifixo na máquina', 'Crossover na polia'],
    'costas': ['Puxada frontal na polia', 'Remada curvada com barra', 'Remada baixa no cabo', 'Barra fixa'],
    'quadriceps': ['Agachamento livre', 'Leg press 45°', 'Cadeira extensora', 'Agachamento búlgaro'],
    'posterior': ['Mesa flexora', 'Stiff com halteres', 'Cadeira flexora', 'Elevação pélvica'],
    'ombros': ['Desenvolvimento com halteres', 'Elevação lateral na polia', 'Crucifixo inverso', 'Elevação frontal'],
    'biceps': ['Rosca direta com barra', 'Rosca alternada com halteres', 'Rosca martelo', 'Rosca Scott'],
    'triceps': ['Tríceps na polia corda', 'Tríceps testa com halteres', 'Tríceps francês', 'Mergulho no banco'],
    'abdomen': ['Abdominal supra no solo', 'Prancha isométrica', 'Abdominal infra na barra', 'Abdominal na polia'],
    'panturrilha': ['Elevação de panturrilha em pé', 'Panturrilha no leg press', 'Panturrilha sentado'],
    'outro': ['Bicicleta ergométrica', 'Esteira / Caminhada', 'Alongamento geral']
}

SQL_TYPES = {Integer: 'INTEGER', Boolean: 'BOOLEAN', DateTime: 'DATETIME', Date: 'DATE',
             Numeric: 'NUMERIC', String: 'TEXT', Text: 'TEXT'}

def _sql_default(col):
    d = col.default
    if d is None or not getattr(d, 'is_scalar', False):
        return ''
    v = d.arg
    if isinstance(v, bool): v = int(v)
    if isinstance(v, (int, float)): return f' DEFAULT {v}'
    return " DEFAULT '" + str(v).replace("'", "''") + "'"

def auto_migrate():
    """Adiciona ao SQLite toda coluna declarada nos modelos que ainda não exista no banco.
    Evita erros 'no such column' ao atualizar bancos criados em versões anteriores."""
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {r[1] for r in conn.execute(text(f'PRAGMA table_info("{table.name}")'))}
            for col in table.columns:
                if col.name in existing:
                    continue
                sql_type = next((v for k, v in SQL_TYPES.items() if isinstance(col.type, k)), 'TEXT')
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {sql_type}{_sql_default(col)}'))

# Reclassificação dos exercícios herdados da v1.0 (grupos genéricos como "Braços" e "Pernas").
LEGACY_NAME_GROUPS = [
    ('tríceps', 'triceps'), ('triceps', 'triceps'), ('rosca', 'biceps'),
    ('panturrilha', 'panturrilha'), ('flexora', 'posterior'), ('stiff', 'posterior'),
    ('pélvica', 'posterior'), ('agachamento', 'quadriceps'), ('leg press', 'quadriceps'),
    ('extensora', 'quadriceps'), ('supino', 'peito'), ('crucifixo', 'peito'),
    ('puxada', 'costas'), ('remada', 'costas'), ('desenvolvimento', 'ombros'),
    ('elevação lateral', 'ombros'), ('abdominal', 'abdomen'), ('prancha', 'abdomen'),
]
LEGACY_MUSCLE_GROUPS = {'peito': 'peito', 'costas': 'costas', 'pernas': 'quadriceps', 'ombros': 'ombros',
                        'braços': 'biceps', 'abdômen': 'abdomen'}

def classify_legacy(name, muscle):
    n = (name or '').lower()
    for key, group in LEGACY_NAME_GROUPS:
        if key in n:
            return group
    return LEGACY_MUSCLE_GROUPS.get((muscle or '').strip().lower(), 'outro')

def initialize_database():
    Base.metadata.create_all(engine)
    auto_migrate()  # precisa rodar antes de qualquer consulta ORM
    with DB.begin() as db:
        # Garante existência do usuário id = 1 (Single-User Mode)
        if not db.get(User, 1):
            db.add(User(id=1, name='Atleta'))

        # Popula catálogo de exercícios com categorização anatômica se vazio
        if not db.scalar(select(Exercise.id).limit(1)):
            for muscle, names in CATALOG.items():
                for name in names:
                    db.add(Exercise(name=name, muscle_group=muscle, legacy_muscle=muscle, custom=False))

        # Exercícios vindos da v1.0: o rótulo antigo (ex.: 'Braços', 'Pernas') ou migração parcial anterior
        # é ajustado pelo nome para o grupo anatômico exato (ex.: Tríceps -> triceps, Flexora -> posterior).
        for e in db.scalars(select(Exercise)):
            legacy = (e.legacy_muscle or '').strip().lower()
            expected = classify_legacy(e.name, e.legacy_muscle or e.muscle_group)
            if legacy not in MUSCLE_GROUPS or e.muscle_group not in MUSCLE_GROUPS or (not e.custom and expected != 'outro' and e.muscle_group != expected):
                e.muscle_group = expected
                e.legacy_muscle = e.muscle_group

        # Treinos antigos sem session_date
        for w in db.scalars(select(Workout).where(Workout.session_date.is_(None))):
            w.session_date = w.started_at.strftime('%Y-%m-%d')

        # Rotinas vindas da v1.0 sem target_muscle_groups: preenche a partir dos exercícios da rotina
        for r in db.scalars(select(Routine).options(selectinload(Routine.items).selectinload(RoutineItem.exercise))):
            if not (r.target_muscle_groups or '').strip() and r.items:
                groups = []
                for it in r.items:
                    mg = it.exercise.muscle_group if it.exercise else None
                    if mg and mg in MUSCLE_GROUPS and mg not in groups:
                        groups.append(mg)
                if groups:
                    r.target_muscle_groups = ','.join(groups)

initialize_database()

# ---------------------------------------------------------------------------
# Image Compression Pipeline (WebP 1080px, 80% quality)
# ---------------------------------------------------------------------------
def compress_and_save_photo(file_storage):
    filename = f"{uuid.uuid4().hex}.webp"
    dest_path = os.path.join(UPLOAD_FOLDER, filename)
    if HAS_PILLOW:
        img = Image.open(file_storage)
        if img.mode in ('RGBA', 'LA'):
            pass
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        max_width = 1080
        if img.width > max_width:
            new_height = int(img.height * (max_width / img.width))
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        img.save(dest_path, format='WEBP', quality=80, method=4)
    else:
        file_storage.save(dest_path)
    return f"/api/evolution/photo/{filename}"

# ---------------------------------------------------------------------------
# Request Utilities, Single-User Authentication & Timing
# ---------------------------------------------------------------------------
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

def found(db, cls, id):
    obj = db.get(cls, id)
    if obj is None: raise InputError('Registro não encontrado.')
    return obj

# PONTO 1: Bypass de Autenticação Monousuário
@app.before_request
def trusted_single_user_session():
    if 'user_id' not in session:
        session['user_id'] = 1
    if 'csrf' not in session:
        session['csrf'] = secrets.token_hex(32)

def authenticated(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        # Modo Monousuário Confiável: requisições têm sessão injetada automaticamente
        session['user_id'] = 1
        return fn(*args, **kwargs)
    return wrapped

@app.before_request
def csrf_check():
    if request.method in ('POST', 'PUT', 'DELETE'):
        # Permite uploads multipart/form-data com token enviado no header ou campo
        token = session.get('csrf')
        header_token = request.headers.get('X-CSRF-Token', '')
        form_token = request.form.get('csrf_token', '') if request.form else ''
        candidate = header_token or form_token
        if not token or not candidate or not secrets.compare_digest(token, candidate):
            return jsonify(error='Sessão expirada. Atualize a página e tente novamente.'), 403

@app.errorhandler(InputError)
def invalid(e): return jsonify(error=str(e)), 400

@app.errorhandler(IntegrityError)
def conflict(e): return jsonify(error='Esse nome já existe ou o registro está em uso.'), 409

@app.errorhandler(413)
def oversized(e): return jsonify(error='Arquivo ou formulário muito grande (limite 16MB).'), 413

@app.errorhandler(500)
def failed(e): return jsonify(error='Não foi possível concluir. Tente novamente.'), 500

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
    response.headers['Cache-Control'] = 'no-store'
    return response

# Serve static uploaded files
@app.route('/api/evolution/photo/<path:filename>')
def serve_evolution_photo(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ---------------------------------------------------------------------------
# API Routes: Health, Auth & System Info
# ---------------------------------------------------------------------------
@app.get('/api/health')
def health():
    with engine.connect() as c: c.execute(text('SELECT 1'))
    return jsonify(status='ok', version=VERSION, is_termux=IS_TERMUX)

@app.get('/api/auth')
def auth():
    if 'csrf' not in session: session['csrf'] = secrets.token_hex(32)
    session['user_id'] = 1
    return jsonify(
        csrf=session['csrf'],
        authenticated=True,
        single_user=True,
        version=VERSION,
        user=dict(id=1, name='Atleta')
    )

@app.post('/api/logout')
def logout():
    # Modo monousuário: renova o token CSRF
    session['csrf'] = secrets.token_hex(32)
    return jsonify(ok=True)

# ---------------------------------------------------------------------------
# API Routes: Biometria e Peso Corporal com Deltas (PONTO 4)
# ---------------------------------------------------------------------------
@app.get('/api/metrics/weight')
@authenticated
def metrics_weight_list():
    with DB() as db:
        rows = list(db.scalars(select(BodyMetric).order_by(BodyMetric.recorded_at.asc())))
        result = []
        prev_weight = None
        for r in rows:
            w = float(r.weight)
            delta = round(w - prev_weight, 2) if prev_weight is not None else 0.0
            result.append(dict(
                id=r.id,
                weight=w,
                delta=delta,
                notes=r.notes or '',
                recorded_at=r.recorded_at
            ))
            prev_weight = w
        return jsonify(list(reversed(result)))

@app.post('/api/metrics/weight')
@authenticated
def metrics_weight_save():
    d = data()
    try:
        w = float(Decimal(str(d.get('weight'))))
        if not 20 <= w <= 500: raise ValueError()
    except (ValueError, TypeError, InvalidOperation):
        raise InputError('Peso: informe um valor numérico válido entre 20 e 500 kg.')
    
    rec_date = (d.get('recorded_at') or now().strftime('%Y-%m-%d')).strip()[:10]
    try:
        datetime.strptime(rec_date, '%Y-%m-%d')
    except ValueError:
        raise InputError('Data inválida (formato esperado AAAA-MM-DD).')
    
    note_text = notes(d)
    with DB.begin() as db:
        existing = db.scalar(select(BodyMetric).where(BodyMetric.recorded_at == rec_date))
        if existing:
            existing.weight = w
            existing.notes = note_text
            metric = existing
        else:
            metric = BodyMetric(weight=w, notes=note_text, recorded_at=rec_date)
            db.add(metric)
        db.flush()
        return jsonify(id=metric.id, weight=float(metric.weight), recorded_at=metric.recorded_at, notes=metric.notes)

@app.delete('/api/metrics/weight/<int:id>')
@authenticated
def metrics_weight_delete(id):
    with DB.begin() as db:
        m = found(db, BodyMetric, id)
        db.delete(m)
    return jsonify(ok=True)

# ---------------------------------------------------------------------------
# API Routes: Galeria de Fotos de Evolução Física (PONTO 2)
# ---------------------------------------------------------------------------
@app.get('/api/evolution/photos')
@authenticated
def evolution_photos_list():
    with DB() as db:
        photos = list(db.scalars(select(EvolutionPhoto).order_by(EvolutionPhoto.taken_at.desc(), EvolutionPhoto.id.desc())))
        return jsonify([dict(
            id=p.id,
            photo_path=p.photo_path,
            angle=p.angle,
            taken_at=p.taken_at,
            metric_id=p.metric_id
        ) for p in photos])

@app.post('/api/evolution/photos')
@authenticated
def evolution_photos_upload():
    if 'photo' not in request.files:
        raise InputError('Selecione uma foto para enviar.')
    photo_file = request.files['photo']
    if not photo_file.filename:
        raise InputError('Arquivo inválido.')
    
    angle = (request.form.get('angle') or 'frontal').strip().lower()
    if angle not in ('frontal', 'costas', 'lateral', 'outro'):
        angle = 'frontal'
    
    taken_at = (request.form.get('taken_at') or now().strftime('%Y-%m-%d')).strip()[:10]
    metric_id_val = request.form.get('metric_id')
    metric_id = int(metric_id_val) if metric_id_val and str(metric_id_val).isdigit() else None

    try:
        saved_path = compress_and_save_photo(photo_file)
    except Exception as e:
        app.logger.warning("Falha na compressão da foto: %s", e)
        raise InputError('Não foi possível processar a imagem.')

    with DB.begin() as db:
        p = EvolutionPhoto(photo_path=saved_path, angle=angle, taken_at=taken_at, metric_id=metric_id)
        db.add(p)
        db.flush()
        return jsonify(id=p.id, photo_path=p.photo_path, angle=p.angle, taken_at=p.taken_at)

@app.delete('/api/evolution/photos/<int:id>')
@authenticated
def evolution_photos_delete(id):
    with DB.begin() as db:
        p = found(db, EvolutionPhoto, id)
        filename = os.path.basename(p.photo_path)
        disk_file = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(disk_file):
            try: os.remove(disk_file)
            except Exception: pass
        db.delete(p)
    return jsonify(ok=True)

# ---------------------------------------------------------------------------
# API Routes: Catálogo Anatômico de Exercícios (PONTO 8 e PONTO 9)
# ---------------------------------------------------------------------------
def ex_dict(e):
    return dict(id=e.id, name=e.name, muscle_group=e.muscle_group or 'outro', equipment=e.equipment, custom=e.custom)

@app.get('/api/exercises')
@authenticated
def exercises():
    muscle = request.args.get('muscle', '').strip().lower()
    with DB() as db:
        query = select(Exercise)
        if muscle and muscle in MUSCLE_GROUPS:
            query = query.where(Exercise.muscle_group == muscle)
        rows = db.scalars(query.order_by(Exercise.muscle_group, Exercise.name)).all()
        return jsonify([ex_dict(e) for e in rows])

catalog_lock = Lock()

@app.route('/api/exercises', methods=['POST'])
@app.route('/api/exercises/<int:id>', methods=['PUT', 'DELETE'])
@authenticated
def exercise_edit(id=None):
    with catalog_lock, DB.begin() as db:
        e = found(db, Exercise, id) if id else Exercise(custom=True)
        if request.method == 'DELETE':
            if not e.custom:
                raise InputError('Exercícios do catálogo padrão não podem ser excluídos.')
            if db.scalar(select(RoutineItem.id).where(RoutineItem.exercise_id == id).limit(1)):
                raise InputError('Remova o exercício de todas as rotinas antes de excluir.')
            for w in db.scalars(select(WorkoutItem).where(WorkoutItem.exercise_id == id)):
                w.exercise_id = None
            db.delete(e)
            return jsonify(ok=True)

        d = data()
        e.name = string(d.get('name'), 'Nome')
        group = (d.get('muscle_group') or d.get('muscle') or 'outro').strip().lower()
        if group not in MUSCLE_GROUPS:
            group = 'outro'
        e.muscle_group = group
        e.legacy_muscle = group
        e.equipment = string(d.get('equipment', ''), 'Equipamento', 100) if d.get('equipment') else ''
        db.add(e)
        db.flush()
        return jsonify(ex_dict(e))

# ---------------------------------------------------------------------------
# API Routes: Rotinas Anatômicas (PONTO 8 e PONTO 9)
# ---------------------------------------------------------------------------
def routine_dict(r):
    return dict(
        id=r.id,
        name=r.name,
        target_muscle_groups=r.target_muscle_groups or '',
        day_of_week=r.day_of_week,
        items=[dict(
            exercise_id=i.exercise_id,
            name=i.exercise.name if i.exercise else 'Exercício',
            muscle_group=i.exercise.muscle_group if i.exercise else 'outro',
            sets=i.sets,
            reps=i.reps,
            rest=i.rest,
            target_reps=i.target_reps
        ) for i in r.items]
    )

def set_routine(db, r, d):
    r.name = string(d.get('name'), 'Nome da rotina')
    r.target_muscle_groups = (d.get('target_muscle_groups') or '').strip().lower()[:255]
    r.day_of_week = d.get('day_of_week') if isinstance(d.get('day_of_week'), int) else None
    items = d.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 25:
        raise InputError('A rotina deve ter entre 1 e 25 exercícios.')
    r.items.clear()
    derived_groups = []
    for pos, i in enumerate(items):
        if not isinstance(i, dict): raise InputError('Exercício inválido.')
        ex = found(db, Exercise, integer(i.get('exercise_id'), 'Exercício', 1, 1000000))
        if ex.muscle_group in MUSCLE_GROUPS and ex.muscle_group not in derived_groups:
            derived_groups.append(ex.muscle_group)
        r.items.append(RoutineItem(
            exercise=ex,
            position=pos,
            sets=integer(i.get('sets'), 'Séries', 1, 20),
            reps=integer(i.get('reps'), 'Repetições', 1, 1000),
            rest=integer(i.get('rest'), 'Descanso', 0, 600),
            target_reps=str(i.get('target_reps') or f"{i.get('reps', 10)}")[:20]
        ))
    if not r.target_muscle_groups and derived_groups:
        r.target_muscle_groups = ','.join(derived_groups)

@app.get('/api/routines')
@authenticated
def routines():
    with DB() as db:
        rows = db.scalars(select(Routine).options(
            selectinload(Routine.items).selectinload(RoutineItem.exercise)
        ).order_by(Routine.id)).all()
        return jsonify([routine_dict(r) for r in rows])

@app.route('/api/routines', methods=['POST'])
@app.route('/api/routines/<int:id>', methods=['PUT', 'DELETE'])
@authenticated
def routine_edit(id=None):
    with DB.begin() as db:
        r = found(db, Routine, id) if id else Routine()
        if request.method == 'DELETE':
            db.delete(r)
            return jsonify(ok=True)
        set_routine(db, r, data())
        db.add(r)
        db.flush()
        return jsonify(routine_dict(r))

# ---------------------------------------------------------------------------
# API Routes: Execução de Treinos & Ergonomia (Auto-preenchimento de Cargas)
# ---------------------------------------------------------------------------
def workout_dict(w):
    return dict(
        id=w.id,
        routine_name=w.routine_name,
        routine_id=w.routine_id,
        started_at=w.started_at.replace(tzinfo=tz).isoformat(),
        finished_at=w.finished_at.replace(tzinfo=tz).isoformat() if w.finished_at else None,
        session_date=w.session_date or w.started_at.strftime('%Y-%m-%d'),
        notes=w.notes,
        items=[dict(
            id=i.id,
            exercise_id=i.exercise_id,
            name=i.name,
            rest=i.rest,
            notes=i.notes,
            sets=[dict(
                id=s.id,
                position=s.position,
                reps=s.reps,
                load=float(s.load),
                done=s.done,
                rpe=float(s.rpe) if s.rpe else None
            ) for s in i.sets]
        ) for i in w.items]
    )

@app.get('/api/workouts')
@authenticated
def workouts():
    month = request.args.get('month', '')
    try:
        start = datetime.strptime(month, '%Y-%m')
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    except ValueError:
        raise InputError('Mês inválido.')
    with DB() as db:
        ws = db.scalars(select(Workout).options(
            selectinload(Workout.items).selectinload(WorkoutItem.sets)
        ).where(
            Workout.finished_at.is_not(None),
            Workout.started_at >= start,
            Workout.started_at < end
        ).order_by(Workout.started_at.desc())).all()
        return jsonify([workout_dict(w) for w in ws])

@app.get('/api/workouts/active')
@authenticated
def active():
    with DB() as db:
        w = db.scalar(select(Workout).options(
            selectinload(Workout.items).selectinload(WorkoutItem.sets)
        ).where(Workout.finished_at.is_(None)).order_by(Workout.id.desc()))
        return jsonify(workout_dict(w) if w else None)

workout_lock = Lock()

@app.post('/api/workouts')
@authenticated
def start_workout():
    with workout_lock, DB.begin() as db:
        if db.scalar(select(Workout.id).where(Workout.finished_at.is_(None)).limit(1)):
            raise InputError('Já existe um treino em andamento. Retome ou descarte esse treino.')
        d = data()
        r = found(db, Routine, integer(d.get('routine_id'), 'Rotina', 1, 1000000))
        entry = found(db, Schedule, integer(d['schedule_id'], 'Agendamento', 1, 1000000)) if d.get('schedule_id') else None
        if entry and (entry.routine_id != r.id or entry.workout_id):
            raise InputError('Agendamento já iniciado ou rotina inválida.')

        current_time = now()
        today_str = current_time.strftime('%Y-%m-%d')
        w = Workout(
            routine_name=r.name,
            routine_id=r.id,
            started_at=current_time,
            session_date=today_str,
            notes=''
        )

        # Pré-preenchimento inteligente de cargas e repetições anteriores para ergonomia
        for pos, i in enumerate(r.items):
            last_load = 0.0
            last_reps = i.reps
            if i.exercise_id:
                last_set = db.execute(
                    select(WorkoutSet.load, WorkoutSet.reps)
                    .join(WorkoutItem, WorkoutItem.id == WorkoutSet.item_id)
                    .join(Workout, Workout.id == WorkoutItem.workout_id)
                    .where(WorkoutItem.exercise_id == i.exercise_id, Workout.finished_at.is_not(None), WorkoutSet.done.is_(True))
                    .order_by(Workout.started_at.desc(), WorkoutSet.position.desc())
                    .limit(1)
                ).first()
                if last_set:
                    last_load = float(last_set[0])
                    last_reps = int(last_set[1])

            item = WorkoutItem(
                exercise_id=i.exercise_id,
                name=i.exercise.name if i.exercise else 'Exercício',
                position=pos,
                rest=i.rest,
                notes='',
                sets=[WorkoutSet(position=n, reps=last_reps, load=last_load, done=False) for n in range(i.sets)]
            )
            w.items.append(item)

        db.add(w)
        db.flush()
        if entry: entry.workout_id = w.id
        return jsonify(workout_dict(w))

@app.route('/api/workouts/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@authenticated
def workout_edit(id):
    with workout_lock, DB.begin() as db:
        w = db.scalar(select(Workout).options(
            selectinload(Workout.items).selectinload(WorkoutItem.sets)
        ).where(Workout.id == id))
        if w is None: raise InputError('Registro não encontrado.')
        if request.method == 'GET': return jsonify(workout_dict(w))
        if request.method == 'DELETE':
            for entry in db.scalars(select(Schedule).where(Schedule.workout_id == w.id)):
                entry.workout_id = None
            db.delete(w)
            return jsonify(ok=True)
        if w.finished_at: raise InputError('Treino já finalizado.')

        d = data()
        w.notes = notes(d)
        items = d.get('items')
        if not isinstance(items, list) or len(items) != len(w.items):
            raise InputError('Exercícios inválidos.')
        for saved, edit in zip(w.items, items):
            if not isinstance(edit, dict) or edit.get('id') != saved.id:
                raise InputError('Exercício inválido.')
            saved.notes = notes(edit)
            ss = edit.get('sets')
            if not isinstance(ss, list) or len(ss) != len(saved.sets):
                raise InputError('Séries inválidas.')
            for s, v in zip(saved.sets, ss):
                if not isinstance(v, dict) or v.get('id') != s.id or not isinstance(v.get('done'), bool):
                    raise InputError('Série inválida.')
                s.reps = integer(v.get('reps'), 'Repetições', 0, 1000)
                s.load = load_value(v.get('load'))
                s.done = v['done']
                if v.get('rpe') is not None and str(v.get('rpe')).strip():
                    try: s.rpe = float(v.get('rpe'))
                    except Exception: s.rpe = None
                if s.done and s.reps == 0:
                    raise InputError('Série concluída precisa ter repetições.')

        if d.get('finish'):
            if not any(s.done for i in w.items for s in i.sets):
                raise InputError('Conclua pelo menos uma série antes de finalizar.')
            w.finished_at = now()

        db.flush()
        return jsonify(workout_dict(w))

# ---------------------------------------------------------------------------
# API Routes: Histórico de Séries e Cargas
# ---------------------------------------------------------------------------
@app.get('/api/history/<int:id>')
@authenticated
def history(id):
    with DB() as db:
        rows = db.execute(
            select(Workout.started_at, WorkoutItem.name, WorkoutSet.reps, WorkoutSet.load)
            .join(WorkoutItem, WorkoutItem.workout_id == Workout.id)
            .join(WorkoutSet, WorkoutSet.item_id == WorkoutItem.id)
            .where(WorkoutItem.exercise_id == id, Workout.finished_at.is_not(None), WorkoutSet.done.is_(True))
            .order_by(Workout.started_at, WorkoutSet.position)
        ).all()
        return jsonify([dict(
            date=r[0].replace(tzinfo=tz).isoformat(),
            name=r[1],
            reps=r[2],
            load=float(r[3])
        ) for r in rows])

@app.get('/api/history')
@authenticated
def history_batch():
    values = request.args.get('ids', '').split(',')
    ids = list({integer(v, 'Exercício', 1, 1000000) for v in values if v})
    if len(ids) > 25: raise InputError('Máximo de 25 exercícios.')
    with DB() as db:
        rows = db.execute(
            select(WorkoutItem.exercise_id, Workout.started_at, WorkoutItem.name, WorkoutSet.reps, WorkoutSet.load)
            .join(WorkoutItem, WorkoutItem.workout_id == Workout.id)
            .join(WorkoutSet, WorkoutSet.item_id == WorkoutItem.id)
            .where(WorkoutItem.exercise_id.in_(ids), Workout.finished_at.is_not(None), WorkoutSet.done.is_(True))
            .order_by(Workout.started_at, WorkoutSet.position)
        ).all()
        result = {i: [] for i in ids}
        for r in rows:
            result[r[0]].append(dict(
                date=r[1].replace(tzinfo=tz).isoformat(),
                name=r[2],
                reps=r[3],
                load=float(r[4])
            ))
        return jsonify(result)

# ---------------------------------------------------------------------------
# API Routes: Calendário Inteligente e Matriz Temporal (PONTO 7)
# ---------------------------------------------------------------------------
@app.get('/api/calendar/month')
@authenticated
def calendar_month():
    month = request.args.get('month', now().strftime('%Y-%m'))
    try:
        start = datetime.strptime(month, '%Y-%m')
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    except ValueError:
        raise InputError('Mês inválido.')
    with DB() as db:
        ws = list(db.scalars(select(Workout).where(
            Workout.started_at >= start,
            Workout.started_at < end,
            Workout.finished_at.is_not(None)
        )))
        scs = list(db.scalars(select(Schedule).where(
            Schedule.scheduled_at >= start,
            Schedule.scheduled_at < end
        )))
        trained_dates = {w.started_at.strftime('%Y-%m-%d') for w in ws}
        scheduled_dates = {s.scheduled_at.strftime('%Y-%m-%d') for s in scs if not s.workout_id}
        return jsonify(
            month=month,
            trained_dates=list(trained_dates),
            scheduled_dates=list(scheduled_dates)
        )

@app.get('/api/calendar/day/<date_str>')
@authenticated
def calendar_day_state(date_str):
    try:
        target_date = datetime.strptime(date_str[:10], '%Y-%m-%d').date()
    except ValueError:
        raise InputError('Data inválida (formato esperado AAAA-MM-DD).')
    
    today = today_date()
    is_past = target_date < today
    is_today = target_date == today
    is_future = target_date > today

    start_dt = datetime.combine(target_date, datetime.min.time())
    end_dt = datetime.combine(target_date, datetime.max.time())

    with DB() as db:
        workouts = list(db.scalars(select(Workout).options(
            selectinload(Workout.items).selectinload(WorkoutItem.sets)
        ).where(
            Workout.started_at >= start_dt,
            Workout.started_at <= end_dt
        ).order_by(Workout.id.desc())))

        finished_workout = next((w for w in workouts if w.finished_at), None)
        active_workout = next((w for w in workouts if not w.finished_at), None)

        schedules = list(db.scalars(select(Schedule).where(
            Schedule.scheduled_at >= start_dt,
            Schedule.scheduled_at <= end_dt
        )))

        # Matriz de Estados Temporais (RF07)
        if is_past:
            state = 'past_trained' if finished_workout else 'past_rest'
            can_schedule = False
        elif is_today:
            if finished_workout:
                state = 'today_trained'
                can_schedule = False
            elif active_workout or schedules:
                state = 'today_ready'
                can_schedule = False
            else:
                state = 'today_idle'
                can_schedule = True
        else: # Futuro
            state = 'future_scheduled' if schedules else 'future_empty'
            can_schedule = True

        chosen_workout = finished_workout or active_workout

        return jsonify(
            date=date_str[:10],
            state=state,
            is_past=is_past,
            is_today=is_today,
            is_future=is_future,
            can_schedule=can_schedule,
            workout=workout_dict(chosen_workout) if chosen_workout else None,
            schedules=[dict(
                id=s.id,
                routine_id=s.routine_id,
                routine_name=s.routine_name,
                scheduled_at=s.scheduled_at.strftime('%Y-%m-%dT%H:%M')
            ) for s in schedules]
        )

# Agendamentos legados para compatibilidade
@app.get('/api/schedules')
@authenticated
def schedules_list():
    month = request.args.get('month', '')
    try:
        start = datetime.strptime(month, '%Y-%m')
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    except ValueError:
        raise InputError('Mês inválido.')
    with DB() as db:
        entries = db.scalars(select(Schedule).where(
            Schedule.scheduled_at >= start,
            Schedule.scheduled_at < end
        ).order_by(Schedule.scheduled_at)).all()
        return jsonify([dict(
            id=e.id,
            routine_id=e.routine_id,
            routine_name=e.routine_name,
            scheduled_at=e.scheduled_at.replace(tzinfo=tz).isoformat(),
            workout_id=e.workout_id,
            status=('concluído' if e.workout_id and (w := db.get(Workout, e.workout_id)) and w.finished_at else
                    'em andamento' if e.workout_id and db.get(Workout, e.workout_id) else 'agendado')
        ) for e in entries])

schedule_lock = Lock()

@app.post('/api/schedules')
@authenticated
def schedule_create():
    d = data()
    try:
        stamp = datetime.strptime(d.get('scheduled_at', ''), '%Y-%m-%dT%H:%M')
    except (ValueError, TypeError):
        raise InputError('Informe uma data e horário válidos.')
    
    # Bloqueio de agendamento em datas passadas (RF07)
    if stamp.date() < today_date():
        raise InputError('Não é permitido agendar treinos em datas passadas.')

    with schedule_lock, DB.begin() as db:
        r = found(db, Routine, integer(d.get('routine_id'), 'Rotina', 1, 1000000))
        if db.scalar(select(Schedule.id).where(Schedule.routine_id == r.id, Schedule.scheduled_at == stamp)):
            raise InputError('Esta rotina já está agendada neste horário.')
        entry = Schedule(routine_id=r.id, routine_name=r.name, scheduled_at=stamp)
        db.add(entry)
        db.flush()
        return jsonify(id=entry.id)

@app.delete('/api/schedules/<int:id>')
@authenticated
def schedule_delete(id):
    with DB.begin() as db:
        db.delete(found(db, Schedule, id))
    return jsonify(ok=True)

# ---------------------------------------------------------------------------
# API Routes: Notificações Web Push (RFC 8291 / 8292)
# ---------------------------------------------------------------------------
VAPID_PRIVATE_KEY_PATH = os.path.expanduser('~/.local/share/ritmo/vapid_private.pem')
if IS_TERMUX:
    VAPID_PRIVATE_KEY_PATH = '/data/data/com.termux/files/home/.local/share/ritmo/vapid_private.pem'

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
        app.logger.warning("Erro ao carregar chave VAPID: %s", e)
        return ''

VAPID_PUBLIC_KEY = get_vapid_public_key()

@app.get('/api/push/public_key')
@authenticated
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
    if not endpoint or not p256dh or not auth or not endpoint.startswith('https://'):
        raise InputError('Inscrição push inválida.')
    with DB.begin() as db:
        existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
        if existing:
            existing.p256dh = p256dh
            existing.auth = auth
            existing.user_agent = request.headers.get('User-Agent', '')[:255]
        else:
            # Limita a 10 dispositivos para monousuário
            subs = list(db.scalars(select(PushSubscription).order_by(PushSubscription.id.asc())))
            if len(subs) >= 10:
                db.delete(subs[0])
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
                import json
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
                    except Exception as e:
                        app.logger.warning("Erro push individual: %s", e)
            except Exception as e:
                app.logger.warning("Módulo WebPush indisponível: %s", e)
    return jsonify(sent=sent, total=subs_count)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)

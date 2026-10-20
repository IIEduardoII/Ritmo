import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parent.parent
data = Path.home() / '.local' / 'share' / 'ritmo'
data.mkdir(parents=True, exist_ok=True)
env_file = root / '.env'
if env_file.exists():
    raise SystemExit('.env já existe; preservado.')

database = data / 'ritmo.sqlite3'
content = (
    f"DATABASE_URL=sqlite:///{database}\n"
    f"SECRET_KEY={secrets.token_hex(32)}\n"
    "COOKIE_SECURE=false\n"
    "GEMINI_ENABLED=false\n"
    "GEMINI_FREE_PROJECT_CONFIRMED=false\n"
    "GEMINI_API_KEY=\n"
)
fd = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write(content)
print(f'.env criado com permissão 600; banco SQLite em {database}.')

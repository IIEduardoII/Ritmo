import getpass
import secrets
from app import Account, DB, ph

password = getpass.getpass('Nova senha (mínimo de 12 caracteres): ')
if len(password) < 12 or len(password) > 256:
    raise SystemExit('Use de 12 a 256 caracteres.')
if getpass.getpass('Confirme a senha: ') != password:
    raise SystemExit('As senhas não coincidem.')
with DB.begin() as db:
    account = db.get(Account, 1)
    if not account:
        account = Account(id=1)
        db.add(account)
    account.password_hash = ph.hash(password)
    account.version = secrets.token_hex(32)
print('Senha configurada. Sessões anteriores foram invalidadas.')

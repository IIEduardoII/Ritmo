import os
import secrets
from pathlib import Path
root=Path(__file__).resolve().parent.parent
path=root/'.env'
content='MYSQL_DATABASE=treinos\nMYSQL_USER=treinos\n'+''.join(f'{key}={secrets.token_hex(32)}\n' for key in ['MYSQL_PASSWORD','MYSQL_ROOT_PASSWORD','SECRET_KEY'])+'HTTP_PORT=8088\nCOOKIE_SECURE=true\n'
fd=os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
with os.fdopen(fd,'w') as f:f.write(content)
print('.env criado com permissões 600; nenhum segredo foi exibido.')

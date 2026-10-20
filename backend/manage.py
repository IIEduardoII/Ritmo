import sys
from app import User, DB

print("Ritmo v1.1.0 - Gestão de Perfil Monousuário")
with DB.begin() as db:
    u = db.get(User, 1)
    if not u:
        u = User(id=1, name='Atleta')
        db.add(u)
    print(f"Usuário ativo: id={u.id}, nome='{u.name}'")
    if len(sys.argv) > 1:
        new_name = sys.argv[1].strip()
        if new_name:
            u.name = new_name
            print(f"Nome atualizado para '{u.name}'.")
print("Modo Single-User ativo: login por senha desabilitado (acesso local/Tailscale direto).")

"""Teste de integração: pode usar SQLite temporário ou MySQL isolado."""
import os
import secrets
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
os.environ.setdefault('SECRET_KEY',secrets.token_hex(32))
os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path('/tmp')/('treinos-check-'+secrets.token_hex(8)+'.db')))
from app import app, DB, Account, ph
password=secrets.token_urlsafe(24)
with DB.begin() as db:
    assert db.get(Account,1) is None, 'Execute apenas em banco isolado sem usuário!'
    db.add(Account(id=1,password_hash=ph.hash(password),version=secrets.token_hex(32)))
c=app.test_client();token=c.get('/api/auth').json['csrf']
def call(path, method='GET',data=None):
    return c.open('/api/'+path,method=method,json=data,headers={'X-CSRF-Token':token})
assert call('routines').status_code==401
assert c.post('/api/login',json={'password':password}).status_code==403
assert call('login','POST',{'password':'senha-errada'}).status_code==401
r=call('login','POST',{'password':password});assert r.status_code==200;token=r.json['csrf']
assert len(call('exercises').json)>=18
ex=call('exercises','POST',{'name':'Exercício teste','muscle':'Costas'}).json
id=ex['id']
assert call('exercises/'+str(id),'PUT',{'name':'Exercício editado','muscle':'Costas'}).status_code==200
suggest=call('suggest','POST',{'goal':'força','days':4,'minutes':45});assert len(suggest.json['routines'])==4
assert call('routines').json==[] # Sugestão ainda não foi salva.
assert call('suggest','POST',{'goal':'força','days':7,'minutes':45}).status_code==400
routine={'name':'Rotina teste','goal':'hipertrofia','items':[{'exercise_id':id,'sets':2,'reps':10,'rest':60}]}
r=call('routines','POST',routine);assert r.status_code==200;r_id=r.json['id']
routine['name']='Rotina editada';assert call('routines/'+str(r_id),'PUT',routine).status_code==200
assert call('exercises/'+str(id),'DELETE').status_code==400
w=call('workouts','POST',{'routine_id':r_id}).json
assert call('workouts','POST',{'routine_id':r_id}).status_code==400
from app import now
month=now().strftime('%Y-%m')
assert call('workouts?month='+month).json==[]
w['items'][0]['sets'][0].update(done=True,load=20.5,reps=10)
w['notes']='Teste de sessão';w['items'][0]['notes']='Sem aumento recomendado'
assert call('workouts/'+str(w['id']),'PUT',w).status_code==200
w['items'][0]['sets'][0]['load']=-1
assert call('workouts/'+str(w['id']),'PUT',w).status_code==400
w['items'][0]['sets'][0]['load']=20.5;w['finish']=True
assert call('workouts/'+str(w['id']),'PUT',w).status_code==200
assert call('workouts/active').json is None
assert len(call('workouts?month='+month).json)==1
history=call('history/'+str(id)).json;assert len(history)==1 and history[0]['load']==20.5
assert call('routines/'+str(r_id),'DELETE').status_code==200
assert call('exercises/'+str(id),'DELETE').status_code==200
assert call('workouts/'+str(w['id'])).json['items'][0]['name']=='Exercício editado'
assert call('workouts/'+str(w['id']),'DELETE').status_code==200
assert call('logout','POST',{}).status_code==200
assert call('exercises').status_code==401
with DB() as db:
    stored=db.get(Account,1).password_hash
    assert stored.startswith('$argon2id$') and password not in stored
print('OK: login/CSRF, catálogo, CRUD, sugestões, sessão, validação, calendário, histórico, preservação e hash.')

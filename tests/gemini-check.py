"""Integração isolada e transporte simulado; nunca chama Google nem banco de produção."""
import copy
import io
import json
import os
import secrets
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
os.environ['SECRET_KEY']=secrets.token_hex(32)
os.environ['DATABASE_URL']='sqlite:///'+str(Path('/tmp')/('ritmo-ai-check-'+secrets.token_hex(8)+'.db'))
os.environ['GEMINI_ENABLED']='false'
os.environ['GEMINI_FREE_PROJECT_CONFIRMED']='false'
os.environ.pop('GEMINI_API_KEY',None)
import app as module
import gemini
from app import app,DB,Account,Exercise,AISettings,ph
with DB.begin() as db:db.add(Account(id=1,password_hash=ph.hash('only-isolated-test'),version='test'))
c=app.test_client();token=c.get('/api/auth').json['csrf']
def call(path,method='GET',d=None):return c.open('/api/'+path,method=method,json=d,headers={'X-CSRF-Token':token})
assert call('ai/settings').status_code==401
r=call('login','POST',{'password':'only-isolated-test'});token=r.json['csrf']
profile={'goal':'força','experience':'iniciante','days':1,'minutes':45,'equipment':'Halteres','limitations':'Evitar saltos','consent':True}
r=call('ai/settings');assert r.json=={'configured':False,'enabled':False,'model':gemini.MODEL}
with patch.object(gemini,'generate') as generate:
 assert call('ai/suggest','POST',profile).status_code==503
 generate.assert_not_called()
assert call('ai/suggest','POST',{**profile,'consent':False}).status_code==400
os.environ.update(GEMINI_ENABLED='true',GEMINI_FREE_PROJECT_CONFIRMED='true',GEMINI_API_KEY='test-not-a-real-key')
assert call('ai/suggest','POST',profile).status_code==400 # owner disabled
assert call('ai/settings','PUT',{'enabled':True}).json['enabled']
for key,value in [('weight',float('nan')),('height',True),('days',7),('experience','unknown')]:
 assert call('ai/suggest','POST',{**profile,key:value}).status_code==400
plan={'routines':[{'name':'Treino A','items':[{'name':'  SÚPINO   RETO ','muscle':'Peito','sets':3,'reps':10,'rest':60},{'name':'Remada com elástico','muscle':'Costas','sets':2,'reps':12,'rest':60}]}]}
original=call('exercises').json
module.ai_last_request=0
with patch.object(gemini,'generate',return_value=plan) as generate:
 response=call('ai/suggest','POST',{**profile,'ignored-secret':'do-not-send'})
 assert response.status_code==200,response.json
 sent=generate.call_args.args[0]
 assert set(sent)=={'goal','experience','days','minutes','equipment','limitations'}
 assert call('ai/suggest','POST',profile).status_code==429
assert call('routines').json==[] and call('exercises').json==original
assert response.json['routines'][0]['items'][0]['existing_id']
def ask(raw):
 module.ai_last_request=0
 with patch.object(gemini,'generate',return_value=raw):return call('ai/suggest','POST',profile)
for mutate in ['load','unsafe','duplicate','float','extra','empty']:
 bad=copy.deepcopy(plan)
 if mutate=='load':bad['routines'][0]['items'][0]['load']=25
 if mutate=='unsafe':bad['routines'][0]['name']='Tratamento para lesão'
 if mutate=='duplicate':bad['routines'][0]['items'][1]['name']='supinoreto'
 if mutate=='float':bad['routines'][0]['items'][0]['sets']=2.5
 if mutate=='extra':bad['diagnosis']='something'
 if mutate=='empty':bad['routines']=[]
 assert ask(bad).status_code==502,mutate
module.ai_last_request=0
with patch.object(gemini,'generate',side_effect=gemini.GeminiError('Cota gratuita atingida',429)):
 assert call('ai/suggest','POST',profile).status_code==429
assert call('suggest','POST',{'goal':'força','days':1,'minutes':45}).status_code==200
# Se desativado enquanto a resposta chega, nenhum rascunho é devolvido.
def disable_during_generation(_):
 with DB.begin() as db:db.get(AISettings,1).enabled=False
 return plan
module.ai_last_request=0
with patch.object(gemini,'generate',side_effect=disable_during_generation):assert call('ai/suggest','POST',profile).status_code==400
assert call('ai/settings').json['enabled'] is False
# Salvar requer confirmação e revalidação; reutiliza catálogo normalizado e é atômico.
payload={'goal':'força','routine':plan['routines'][0],'reviewed':False}
assert call('ai/import','POST',payload).status_code==400
payload['reviewed']=True
bad=copy.deepcopy(payload);bad['routine']['items'][1]['sets']=99
assert call('ai/import','POST',bad).status_code==400
assert call('exercises').json==original
saved=call('ai/import','POST',payload);assert saved.status_code==200,saved.json
assert saved.json['items'][0]['name']=='Supino reto'
assert len(call('exercises').json)==len(original)+1
assert call('exercises','POST',{'name':'  remáda com   ELÁSTICO','muscle':'Costas'}).status_code==400
assert gemini.normalize(' SÚPINO\tRETO ')==gemini.normalize('supinoreto')
# Transporte: chave somente no cabeçalho, endpoint fixo, sem fallback/retry nem erro remoto vazado.
class FakeResponse(io.BytesIO):pass
api_response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(plan)}]}}]}
with patch.object(gemini.transport,'open',return_value=FakeResponse(json.dumps(api_response).encode())) as open_:
 assert gemini.generate(profile)==plan
 req=open_.call_args.args[0]
 assert req.full_url==gemini.ENDPOINT and 'test-not-a-real-key' not in req.full_url
 assert req.get_header('X-goog-api-key')=='test-not-a-real-key'
 request_body=json.loads(req.data)
 assert request_body['generationConfig']['responseMimeType']=='application/json'
 assert request_body['generationConfig']['thinkingConfig']=={'thinkingLevel':'minimal'}
 assert 'temperature' not in request_body['generationConfig']
 assert 'tools' not in request_body
 assert request_body['generationConfig']['responseJsonSchema']==gemini.WIRE_SCHEMA
 assert 'minimum' not in json.dumps(request_body['generationConfig']['responseJsonSchema'])
 assert gemini.SCHEMA['properties']['routines']['maxItems']==6
for status in [400,401,403,404,429,500]:
 remote=urllib.error.HTTPError(gemini.ENDPOINT,status,'secret-response-do-not-leak',{},io.BytesIO(b'secret-body'))
 with patch.object(gemini.transport,'open',side_effect=remote) as open_:
  try:gemini.generate(profile);assert False
  except gemini.GeminiError as e:
   assert 'secret' not in str(e) and 'test-not-a-real-key' not in str(e)
   assert e.status==(429 if status==429 else 503)
  assert open_.call_count==1
with patch.object(gemini.transport,'open',return_value=FakeResponse(b'not JSON')):
 try:gemini.generate(profile);assert False
 except gemini.GeminiError as e:assert e.status==502
os.environ['GEMINI_FREE_PROJECT_CONFIRMED']='false';assert not gemini.configured()
print('OK: auth/CSRF, opt-in, consentimento, projeto gratuito, cota, resposta estruturada, validação, duplicatas, revisão, atomicidade e ausência de fallback/vazamento.')

os.environ['GEMINI_FREE_PROJECT_CONFIRMED']='true'
# Machine-code diagnosis never records upstream text or the API key.
for status,details,expected in [(400,[{'reason':'API_KEY_INVALID'}],'Chave/configuração'),(400,[],'formato'),(404,[],'Modelo ou endpoint')]:
 remote=urllib.error.HTTPError(gemini.ENDPOINT,status,'do-not-log',{},io.BytesIO(json.dumps({'error':{'message':'secret-body test-not-a-real-key','details':details}}).encode()))
 with patch.object(gemini.transport,'open',side_effect=remote):
  try:gemini.generate(profile);assert False
  except gemini.GeminiError as e:assert expected in str(e) and 'test-not-a-real-key' not in str(e)

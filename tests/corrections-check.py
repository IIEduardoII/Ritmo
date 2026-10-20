"""Isolated regression: seed edits, history, schedules, timing and batched history."""
import os,secrets,sys,statistics,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
os.environ.update(SECRET_KEY=secrets.token_hex(32),DATABASE_URL='sqlite:////tmp/ritmo-corrections-'+secrets.token_hex(8)+'.db',COOKIE_SECURE='false')
import app as m
with m.DB.begin() as db:db.add(m.Account(id=1,password_hash=m.ph.hash('isolated-test-password'),version='test'))
c=m.app.test_client();token=c.get('/api/auth').json['csrf']
def call(path,method='GET',data=None):return c.open('/api/'+path,method=method,json=data,headers={'X-CSRF-Token':token})
token=call('login','POST',{'password':'isolated-test-password'}).json['csrf']
e=call('exercises').json[0]
r=call('routines','POST',dict(name='Histórico preservado',goal='força',items=[dict(exercise_id=e['id'],sets=1,reps=5,rest=30)])).json
w=call('workouts','POST',dict(routine_id=r['id'])).json
w['items'][0]['sets'][0].update(done=True,load=10)
w['finish']=True
assert call('workouts/'+str(w['id']),'PUT',w).status_code==200
assert call('exercises/'+str(e['id']),'PUT',dict(name='Nome inicial editado',muscle='Outro grupo')).status_code==200
assert call('workouts/'+str(w['id'])).json['items'][0]['name']==e['name']
assert call('history/'+str(e['id'])).json[0]['name']==e['name']
assert call('suggest','POST',dict(goal='força',days=2,minutes=30)).status_code==200
month=m.now().strftime('%Y-%m');stamp=month+'-15T06:00'
schedule=call('schedules','POST',dict(routine_id=r['id'],scheduled_at=stamp))
assert schedule.status_code==200,schedule.json
assert call('schedules','POST',dict(routine_id=r['id'],scheduled_at=stamp)).status_code==400
for invalid in ['2026-02-30T06:00','2026-10-15T25:00','no',None]:
 assert call('schedules','POST',dict(routine_id=r['id'],scheduled_at=invalid)).status_code==400
entry=call('schedules?month='+month).json[0]
assert entry['status']=='agendado' and entry['scheduled_at'].endswith('06:00:00-03:00')
sw=call('workouts','POST',dict(routine_id=r['id'],schedule_id=entry['id'])).json
assert call('schedules?month='+month).json[0]['status']=='em andamento'
sw['items'][0]['sets'][0].update(done=True,load=15);sw['finish']=True
assert call('workouts/'+str(sw['id']),'PUT',sw).status_code==200
assert call('schedules?month='+month).json[0]['status']=='concluído'
assert call('workouts','POST',dict(routine_id=r['id'],schedule_id=entry['id'])).status_code==400
assert call('history?ids='+str(e['id'])).json[str(e['id'])]==call('history/'+str(e['id'])).json
assert call('routines/'+str(r['id']),'DELETE').status_code==200
assert call('schedules?month='+month).json[0]['routine_name']=='Histórico preservado'
assert call('schedules/'+str(entry['id']),'DELETE').status_code==200
assert call('workouts/'+str(sw['id'])).status_code==200
# Timings: realistic 12-exercise workout, ten saves. Isolated SQLite, not RF511/MySQL/PWA.
exercises=call('exercises').json[:12]
r=call('routines','POST',dict(name='Medição',goal='força',items=[dict(exercise_id=e['id'],sets=3,reps=8,rest=60) for e in exercises])).json
w=call('workouts','POST',dict(routine_id=r['id'])).json
samples=[]
for n in range(10):
 w['notes']='Medição '+str(n);start=time.perf_counter();response=call('workouts/'+str(w['id']),'PUT',w)
 assert response.status_code==200 and 'db;dur=' in response.headers['Server-Timing']
 samples.append((time.perf_counter()-start)*1000)
print('OK: catálogo inicial editável, snapshots históricos, sugestão manual, calendário/horário/status, validação, duplicatas, histórico em lote e Server-Timing.')
print('SQLite isolado, 12 exercícios / 36 séries, 10 salvamentos: mediana %.2f ms; máximo %.2f ms; último %s'%(statistics.median(samples),max(samples),response.headers['Server-Timing']))

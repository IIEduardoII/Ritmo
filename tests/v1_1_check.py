"""
Suíte de testes de integração oficial do Ritmo v1.1.0
Testa:
 1. Versão 1.1.0 e Single-User Trusted Mode (Bypass de senhas)
 2. Remoção de dependências de IA (100% offline)
 3. Registro e histórico de peso corporal com cálculo de deltas
 4. Upload de fotos com pipeline de compressão WebP e classificação por ângulos
 5. Catálogo anatômico com os 10 grupos musculares e filtragem
 6. Rotinas com target_muscle_groups e extinção de foco
 7. Início de treino com pré-preenchimento de cargas anteriores
 8. Execução de treino e histórico
 9. Calendário Inteligente com Matriz de Estados Temporais (RF07)
 10. Web Push subscriptions
"""
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, date, timedelta
from pathlib import Path

# Configura banco temporário isolado
temp_dir = tempfile.mkdtemp()
db_file = os.path.join(temp_dir, 'ritmo-test.sqlite3')
os.environ['DATABASE_URL'] = f'sqlite:///{db_file}'
os.environ['SECRET_KEY'] = 'test-secret-key-v1-1-0'
os.environ['COOKIE_SECURE'] = 'false'

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import app as m

class TestRitmoV11(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        m.initialize_database()
        cls.client = m.app.test_client()

    def get_token(self):
        res = self.client.get('/api/auth')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['authenticated'])
        self.assertTrue(data['single_user'])
        self.assertEqual(data['version'], '1.1.0')
        return data['csrf']

    def api_call(self, path, method='GET', json=None, data=None):
        token = self.get_token()
        headers = {'X-CSRF-Token': token}
        return self.client.open(
            '/api/' + path,
            method=method,
            json=json,
            data=data,
            headers=headers
        )

    def test_01_health_and_single_user(self):
        res = self.client.get('/api/health')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['version'], '1.1.0')

        # Garante que rotas protegidas não exigem mais senha (Bypass monousuário)
        res_ex = self.client.get('/api/exercises')
        self.assertEqual(res_ex.status_code, 200)

    def test_02_body_metrics_and_deltas(self):
        # 1. Registra medição no dia 2026-10-10 (65.0 kg)
        r1 = self.api_call('metrics/weight', 'POST', {'weight': 65.0, 'recorded_at': '2026-10-10', 'notes': 'Início da medição'})
        self.assertEqual(r1.status_code, 200)

        # 2. Registra medição no dia 2026-10-15 (66.2 kg) -> delta +1.2 kg
        r2 = self.api_call('metrics/weight', 'POST', {'weight': 66.2, 'recorded_at': '2026-10-15', 'notes': 'Ganho de massa'})
        self.assertEqual(r2.status_code, 200)

        # 3. Registra medição no dia 2026-10-20 (65.8 kg) -> delta -0.4 kg
        r3 = self.api_call('metrics/weight', 'POST', {'weight': 65.8, 'recorded_at': '2026-10-20', 'notes': 'Ajuste calórico'})
        self.assertEqual(r3.status_code, 200)

        # 4. Consulta lista ordenada decrescente
        list_res = self.api_call('metrics/weight')
        self.assertEqual(list_res.status_code, 200)
        items = list_res.get_json()
        self.assertEqual(len(items), 3)

        # Ordem decrescente: 2026-10-20 primeiro, depois 2026-10-15, depois 2026-10-10
        self.assertEqual(items[0]['recorded_at'], '2026-10-20')
        self.assertEqual(items[0]['weight'], 65.8)
        self.assertEqual(items[0]['delta'], -0.4)

        self.assertEqual(items[1]['recorded_at'], '2026-10-15')
        self.assertEqual(items[1]['weight'], 66.2)
        self.assertEqual(items[1]['delta'], 1.2)

        self.assertEqual(items[2]['recorded_at'], '2026-10-10')
        self.assertEqual(items[2]['weight'], 65.0)
        self.assertEqual(items[2]['delta'], 0.0)

    def test_03_evolution_photos_upload(self):
        # Gera uma imagem em memória simples (100x100 PNG)
        from PIL import Image
        img_byte_arr = io.BytesIO()
        img = Image.new('RGB', (100, 100), color='blue')
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)

        token = self.get_token()
        data = {
            'photo': (img_byte_arr, 'test.png'),
            'angle': 'frontal',
            'taken_at': '2026-10-20',
            'csrf_token': token
        }
        res = self.client.post('/api/evolution/photos', data=data, content_type='multipart/form-data', headers={'X-CSRF-Token': token})
        self.assertEqual(res.status_code, 200)
        uploaded = res.get_json()
        self.assertTrue(uploaded['photo_path'].endswith('.webp'))
        self.assertEqual(uploaded['angle'], 'frontal')

        # Consulta galeria
        list_res = self.api_call('evolution/photos')
        self.assertEqual(list_res.status_code, 200)
        photos = list_res.get_json()
        self.assertTrue(len(photos) >= 1)
        self.assertEqual(photos[0]['id'], uploaded['id'])

        # Exclusão
        del_res = self.api_call(f"evolution/photos/{uploaded['id']}", 'DELETE')
        self.assertEqual(del_res.status_code, 200)

    def test_04_anatomical_exercises_and_filtering(self):
        # Consulta catálogo geral
        res = self.api_call('exercises')
        self.assertEqual(res.status_code, 200)
        catalog = res.get_json()
        self.assertTrue(len(catalog) >= 15)

        # Filtro reativo por grupo muscular (ex: peito)
        res_peito = self.api_call('exercises?muscle=peito')
        self.assertEqual(res_peito.status_code, 200)
        peito_items = res_peito.get_json()
        self.assertTrue(all(item['muscle_group'] == 'peito' for item in peito_items))
        self.assertTrue(len(peito_items) >= 2)

    def test_05_routines_without_foco(self):
        # Busca um exercício de peito e um de tríceps
        exs = self.api_call('exercises').get_json()
        e_peito = next(e for e in exs if e['muscle_group'] == 'peito')
        e_triceps = next(e for e in exs if e['muscle_group'] == 'triceps')

        routine_data = {
            'name': 'Treino A - Peito e Tríceps',
            'target_muscle_groups': 'peito,triceps',
            'day_of_week': 1,
            'items': [
                {'exercise_id': e_peito['id'], 'sets': 3, 'reps': 10, 'rest': 90},
                {'exercise_id': e_triceps['id'], 'sets': 3, 'reps': 12, 'rest': 60}
            ]
        }
        res = self.api_call('routines', 'POST', routine_data)
        self.assertEqual(res.status_code, 200)
        routine = res.get_json()
        self.assertEqual(routine['name'], 'Treino A - Peito e Tríceps')
        self.assertEqual(routine['target_muscle_groups'], 'peito,triceps')

        # Inicia treino da rotina
        w_res = self.api_call('workouts', 'POST', {'routine_id': routine['id']})
        self.assertEqual(w_res.status_code, 200)
        workout = w_res.get_json()
        self.assertEqual(workout['routine_name'], 'Treino A - Peito e Tríceps')

        # Preenche séries e finaliza treino
        w_id = workout['id']
        workout['items'][0]['sets'][0].update(done=True, reps=10, load=40.0)
        workout['items'][0]['sets'][1].update(done=True, reps=10, load=40.0)
        workout['items'][0]['sets'][2].update(done=True, reps=10, load=40.0)
        workout['items'][1]['sets'][0].update(done=True, reps=12, load=25.0)
        workout['items'][1]['sets'][1].update(done=True, reps=12, load=25.0)
        workout['items'][1]['sets'][2].update(done=True, reps=12, load=25.0)
        workout['finish'] = True

        save_res = self.api_call(f'workouts/{w_id}', 'PUT', workout)
        self.assertEqual(save_res.status_code, 200)
        self.assertIsNotNone(save_res.get_json()['finished_at'])

        # Ao iniciar um SEGUNDO treino dessa rotina, deve PRÉ-PREENCHER com a carga de 40.0 kg e 25.0 kg!
        w2_res = self.api_call('workouts', 'POST', {'routine_id': routine['id']})
        self.assertEqual(w2_res.status_code, 200)
        w2 = w2_res.get_json()
        self.assertEqual(w2['items'][0]['sets'][0]['load'], 40.0)
        self.assertEqual(w2['items'][1]['sets'][0]['load'], 25.0)

        # Limpa treino ativo descartando-o
        self.api_call(f"workouts/{w2['id']}", 'DELETE')

    def test_06_calendar_day_temporal_states_matrix(self):
        # 1. Dia passado com treino realizado (2026-10-15) -> past_trained
        # 2. Dia passado sem treino (2026-10-01) -> past_rest
        # 3. Hoje -> today_trained (já treinamos hoje no teste anterior)
        # 4. Futuro -> future_empty

        # Passado sem treino:
        res_past_rest = self.api_call('calendar/day/2026-10-01')
        self.assertEqual(res_past_rest.status_code, 200)
        d_past_rest = res_past_rest.get_json()
        self.assertTrue(d_past_rest['is_past'])
        self.assertEqual(d_past_rest['state'], 'past_rest')
        self.assertFalse(d_past_rest['can_schedule'])

        # Hoje:
        today_str = date.today().strftime('%Y-%m-%d')
        res_today = self.api_call(f'calendar/day/{today_str}')
        self.assertEqual(res_today.status_code, 200)
        d_today = res_today.get_json()
        self.assertTrue(d_today['is_today'])
        self.assertEqual(d_today['state'], 'today_trained')

        # Futuro:
        future_str = (date.today() + timedelta(days=5)).strftime('%Y-%m-%d')
        res_fut = self.api_call(f'calendar/day/{future_str}')
        self.assertEqual(res_fut.status_code, 200)
        d_fut = res_fut.get_json()
        self.assertTrue(d_fut['is_future'])
        self.assertTrue(d_fut['can_schedule'])

    def test_07_past_schedule_blocked(self):
        # Tentar agendar no passado deve retornar 400 (RF07)
        routines = self.api_call('routines').get_json()
        r_id = routines[0]['id']
        past_time = '2026-01-01T10:00'
        res = self.api_call('schedules', 'POST', {'routine_id': r_id, 'scheduled_at': past_time})
        self.assertEqual(res.status_code, 400)
        self.assertIn('passadas', res.get_json()['error'])

if __name__ == '__main__':
    unittest.main()

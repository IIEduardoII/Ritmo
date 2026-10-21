'use strict';

// ---------------------------------------------------------------------------
// Ritmo v1.1.0 - Single Page Application (100% Vanilla JS, Local-First)
// ---------------------------------------------------------------------------
const localTodayStr = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'America/Sao_Paulo' }).format(new Date());

let csrfToken = '';
let activeWorkout = null;
let selectedMonth = localTodayStr().slice(0, 7);
let timerEnd = null;
let timerPaused = false;
let timerRemaining = 0;
let timerInterval = null;
let reminderEnabled = false;
let pushActive = false;

const $ = sel => document.querySelector(sel);
const main = $('#main');
const dialog = $('#dialog');
const dialogContent = $('#dialog-content');
const confirmDialog = $('#confirm-dialog');

const MUSCLE_LABELS = {
  peito: 'Peito',
  costas: 'Costas',
  quadriceps: 'Quadríceps',
  posterior: 'Posterior',
  ombros: 'Ombros',
  biceps: 'Bíceps',
  triceps: 'Tríceps',
  abdomen: 'Abdômen',
  panturrilha: 'Panturrilha',
  outro: 'Outro'
};

const MUSCLE_ORDER = [
  'peito', 'costas', 'quadriceps', 'posterior',
  'ombros', 'biceps', 'triceps', 'abdomen', 'panturrilha', 'outro'
];

function esc(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]);
}

function normalizeSearch(s) {
  return String(s || '').normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase('pt-BR').trim();
}

let messageTimeout = null;
function notify(text, kind = 'info') {
  const box = $('#message');
  box.textContent = text;
  box.dataset.kind = kind;
  box.hidden = false;
  clearTimeout(messageTimeout);
  messageTimeout = setTimeout(() => { box.hidden = true; }, 4500);
}

function confirmAction(text) {
  return new Promise(resolve => {
    $('#confirm-text').textContent = text;
    confirmDialog.showModal();
    const finish = val => {
      cleanup();
      if (confirmDialog.open) confirmDialog.close();
      resolve(val);
    };
    const yes = () => finish(true);
    const no = () => finish(false);
    const cancel = e => { e.preventDefault(); finish(false); };
    function cleanup() {
      $('#confirm-yes').removeEventListener('click', yes);
      $('#confirm-no').removeEventListener('click', no);
      confirmDialog.removeEventListener('cancel', cancel);
    }
    $('#confirm-yes').addEventListener('click', yes);
    $('#confirm-no').addEventListener('click', no);
    confirmDialog.addEventListener('cancel', cancel);
  });
}

async function api(endpoint, method = 'GET', body = null, isForm = false) {
  const options = {
    method,
    cache: 'no-store',
    headers: { 'X-CSRF-Token': csrfToken }
  };
  if (body) {
    if (isForm) {
      options.body = body;
    } else {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
  }
  const res = await fetch('/api/' + endpoint, options);
  if (!res.ok) {
    let err = 'Erro na requisição.';
    try {
      const data = await res.json();
      if (data && data.error) err = data.error;
    } catch {}
    throw new Error(err);
  }
  return await res.json();
}

function heading(title, subtitle) {
  return `<div class="heading"><div><span class="eyebrow">Ritmo v1.1.0</span><h1>${esc(title)}</h1><p class="muted">${esc(subtitle)}</p></div></div>`;
}

// ---------------------------------------------------------------------------
// Timer de Descanso Persistente com Vibração
// ---------------------------------------------------------------------------
function initTimer() {
  const saved = localStorage.getItem('ritmo.timerEnd');
  if (saved) {
    const end = parseInt(saved, 10);
    if (end > Date.now()) {
      timerEnd = end;
      runTimer();
    } else {
      localStorage.removeItem('ritmo.timerEnd');
    }
  }
}

function startTimer(seconds) {
  if (!seconds || seconds <= 0) return;
  timerEnd = Date.now() + seconds * 1000;
  timerPaused = false;
  localStorage.setItem('ritmo.timerEnd', timerEnd);
  runTimer();
}

function stopTimer() {
  clearInterval(timerInterval);
  localStorage.removeItem('ritmo.timerEnd');
  $('#timer').hidden = true;
}

function runTimer() {
  clearInterval(timerInterval);
  const timerBox = $('#timer');
  const clock = $('#clock');
  const toggleBtn = $('#timer-toggle');
  timerBox.hidden = false;
  toggleBtn.textContent = timerPaused ? 'Continuar' : 'Pausar';

  const updateTick = () => {
    if (timerPaused) return;
    const diff = Math.max(0, Math.ceil((timerEnd - Date.now()) / 1000));
    const m = String(Math.floor(diff / 60)).padStart(2, '0');
    const s = String(diff % 60).padStart(2, '0');
    clock.textContent = `${m}:${s}`;

    if (diff <= 0) {
      stopTimer();
      if (navigator.vibrate) navigator.vibrate([250, 150, 250]);
      notify('Descanso concluído! Hora da próxima série.', 'success');
    }
  };

  updateTick();
  timerInterval = setInterval(updateTick, 400);

  toggleBtn.onclick = () => {
    if (timerPaused) {
      timerEnd = Date.now() + timerRemaining * 1000;
      localStorage.setItem('ritmo.timerEnd', timerEnd);
      timerPaused = false;
      toggleBtn.textContent = 'Pausar';
      updateTick();
    } else {
      timerRemaining = Math.max(0, Math.ceil((timerEnd - Date.now()) / 1000));
      timerPaused = true;
      toggleBtn.textContent = 'Continuar';
    }
  };

  $('#timer-skip').onclick = stopTimer;
}

// ---------------------------------------------------------------------------
// Notificações Web Push (RFC 8291 / 8292)
// ---------------------------------------------------------------------------
function urlB64ToUint8Array(b64) {
  const p = '='.repeat((4 - (b64.length % 4)) % 4);
  const b = (b64 + p).replace(/-/g, '+').replace(/_/g, '/');
  const r = window.atob(b);
  const a = new Uint8Array(r.length);
  for (let i = 0; i < r.length; ++i) a[i] = r.charCodeAt(i);
  return a;
}

async function syncPush() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return false;
  try {
    const reg = await navigator.serviceWorker.ready;
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      const res = await api('push/public_key');
      if (!res.publicKey) return false;
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlB64ToUint8Array(res.publicKey)
      });
    }
    await api('push/subscribe', 'POST', sub.toJSON ? sub.toJSON() : JSON.parse(JSON.stringify(sub)));
    pushActive = true;
    return true;
  } catch (e) {
    console.warn('Push error:', e);
    pushActive = false;
    return false;
  }
}

function bindPushControls() {
  const button = $('#reminders-toggle');
  const testBtn = $('#reminders-test');
  const status = $('#reminders-status');
  if (!button || !status) return;

  const supported = window.isSecureContext && 'Notification' in window;
  const update = () => {
    button.disabled = !supported;
    button.textContent = reminderEnabled ? 'Desativar notificações' : 'Ativar notificações';
    if (testBtn) testBtn.hidden = !reminderEnabled;
    status.textContent = !supported
      ? 'Notificações exigem contexto seguro (HTTPS).'
      : reminderEnabled
        ? (pushActive ? 'Notificações Push ativas (mesmo com o app fechado).' : 'Notificações ativas.')
        : 'Receba lembretes dos seus treinos agendados.';
  };

  button.onclick = async () => {
    if (reminderEnabled) {
      reminderEnabled = false;
      pushActive = false;
      try {
        const reg = await navigator.serviceWorker?.ready;
        const sub = await reg?.pushManager?.getSubscription();
        if (sub) {
          await api('push/unsubscribe', 'POST', { endpoint: sub.endpoint });
          await sub.unsubscribe();
        }
      } catch {}
      update();
      notify('Notificações desativadas.');
      return;
    }
    try {
      button.disabled = true;
      const perm = await Notification.requestPermission();
      if (perm !== 'granted') {
        reminderEnabled = false;
        update();
        notify('Permissão de notificação não concedida.', 'danger');
        return;
      }
      reminderEnabled = true;
      const ok = await syncPush();
      update();
      notify(ok ? 'Notificações Push ativadas!' : 'Notificações locais ativadas.', 'success');
    } catch {
      status.textContent = 'Erro ao configurar notificações.';
    } finally {
      button.disabled = false;
    }
  };

  if (testBtn) {
    testBtn.onclick = async () => {
      try {
        testBtn.disabled = true;
        await syncPush();
        const res = await api('push/test', 'POST', {});
        if (res.sent > 0) {
          notify('Notificação de teste enviada!', 'success');
        } else {
          new Notification('Ritmo · Teste Local', { body: 'Suas notificações estão ativas!' });
          notify('Notificação local disparada.', 'success');
        }
      } catch (err) {
        notify(err.message, 'danger');
      } finally {
        testBtn.disabled = false;
      }
    };
  }

  if (supported && Notification.permission === 'granted') {
    reminderEnabled = true;
    navigator.serviceWorker?.ready
      .then(reg => reg.pushManager.getSubscription())
      .then(sub => { if (sub) pushActive = true; update(); })
      .catch(() => update());
  } else {
    update();
  }
}

// ---------------------------------------------------------------------------
// Micro-Gráfico Minimalista SVG (Zero Libs)
// ---------------------------------------------------------------------------
function renderWeightSvg(metrics) {
  if (!metrics || metrics.length < 2) return '';
  const sorted = [...metrics].reverse(); // cronológico crescente
  const weights = sorted.map(m => m.weight);
  const minW = Math.min(...weights);
  const maxW = Math.max(...weights);
  const range = (maxW - minW) || 1;

  const width = 600;
  const height = 140;
  const paddingX = 45;
  const paddingY = 25;

  const points = sorted.map((m, i) => {
    const x = paddingX + (i / (sorted.length - 1)) * (width - paddingX * 2);
    const y = height - paddingY - ((m.weight - minW) / range) * (height - paddingY * 2);
    return { x: x.toFixed(1), y: y.toFixed(1), w: m.weight, date: m.recorded_at.slice(5).split('-').reverse().join('/') };
  });

  const polyline = points.map(p => `${p.x},${p.y}`).join(' ');

  return `
    <div class="card" style="margin-top:20px;">
      <h3 style="margin-bottom:8px;">Curva de Massa Corporal</h3>
      <svg class="micro-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
        <line x1="${paddingX}" y1="${paddingY}" x2="${width - paddingX}" y2="${paddingY}" stroke="#333" stroke-dasharray="4"/>
        <line x1="${paddingX}" y1="${height - paddingY}" x2="${width - paddingX}" y2="${height - paddingY}" stroke="#333" stroke-dasharray="4"/>
        <text x="4" y="${paddingY + 4}">${maxW.toFixed(1)}kg</text>
        <text x="4" y="${height - paddingY + 4}">${minW.toFixed(1)}kg</text>
        <polyline points="${polyline}" />
        ${points.map(p => `<circle cx="${p.x}" cy="${p.y}" r="4.5"><title>${p.date}: ${p.w} kg</title></circle>`).join('')}
      </svg>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// VIEW 1: Dashboard / Início (#inicio)
// ---------------------------------------------------------------------------
async function dashboardView() {
  const [active, monthData, routines, monthWorkouts] = await Promise.all([
    api('workouts/active'),
    api(`calendar/month?month=${selectedMonth}`),
    api('routines'),
    api(`workouts?month=${selectedMonth}`)
  ]);
  activeWorkout = active;

  const trainedSet = new Set(monthData.trained_dates || []);
  const scheduledSet = new Set(monthData.scheduled_dates || []);
  const todayStr = localTodayStr();
  const [year, month] = selectedMonth.split('-').map(Number);
  const monthDate = new Date(year, month - 1, 2);
  const monthName = monthDate.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });

  const firstDay = new Date(year, month - 1, 1).getDay();
  const daysInMonth = new Date(year, month, 0).getDate();

  let calHtml = '<div class="calendar">';
  ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].forEach(d => {
    calHtml += `<span class="weekday">${d}</span>`;
  });
  for (let i = 0; i < firstDay; i++) calHtml += '<span></span>';
  for (let day = 1; day <= daysInMonth; day++) {
    const dStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    let cls = [];
    if (trainedSet.has(dStr)) cls.push('trained');
    if (scheduledSet.has(dStr)) cls.push('scheduled');
    if (dStr === todayStr) cls.push('today');
    calHtml += `<button type="button" class="${cls.join(' ')}" data-cal-day="${dStr}" aria-label="${day} de ${monthName}">${day}</button>`;
  }
  calHtml += '</div>';

  main.innerHTML = heading('Constância vira evolução.', 'Seu ecossistema local e independente de treino.') + `
    <section class="hero">
      <div>
        <span class="eyebrow">${active ? 'Treino em andamento' : 'Pronto para treinar?'}</span>
        <h2>${active ? esc(active.routine_name) : 'Faça espaço para o seu treino.'}</h2>
        <p>${active ? 'Suas séries salvas estão prontas. Retome de onde parou.' : 'Escolha uma rotina, registre suas séries e acompanhe a evolução.'}</p>
      </div>
      <a class="button" href="${active ? '#treino' : '#rotinas'}">${active ? 'Retomar treino →' : 'Escolher rotina →'}</a>
    </section>

    <div class="stats">
      <div class="stat"><span>Treinos no mês</span><strong>${monthWorkouts.length}</strong></div>
      <div class="stat"><span>Dias treinados</span><strong>${trainedSet.size}</strong></div>
      <div class="stat"><span>Rotinas criadas</span><strong>${routines.length}</strong></div>
    </div>

    <div class="grid">
      <section class="card">
        <div class="row">
          <h2>${esc(monthName)}</h2>
          <input id="month-select" type="month" value="${selectedMonth}" aria-label="Mês do calendário" style="width:auto;">
        </div>
        ${calHtml}
        <p class="muted"><small>● Verde: Concluído &nbsp; ● Borda Dourada: Agendado &nbsp; ▢ Destaque: Hoje</small></p>
        <div style="margin-top:16px;padding-top:14px;border-top:1px solid var(--line);">
          <div class="actions">
            <button id="reminders-toggle" class="secondary compact" type="button">Ativar notificações</button>
            <button id="reminders-test" class="secondary compact" type="button" hidden>Testar Push</button>
          </div>
          <p id="reminders-status" class="muted" style="font-size:12px;margin:8px 0 0;" role="status"></p>
        </div>
      </section>

      <section class="card">
        <h2>Minhas Rotinas</h2>
        ${routines.length ? `
          <div class="routine-list-box">
            ${routines.map(r => `
              <div class="session-row row">
                <div>
                  <strong>${esc(r.name)}</strong>
                  <div class="muted"><small>${esc(r.target_muscle_groups ? r.target_muscle_groups.split(',').map(m => MUSCLE_LABELS[m] || m).join(', ') : 'Geral')} · ${r.items.length} exercícios</small></div>
                </div>
                <button class="secondary compact" data-start-routine="${r.id}">Iniciar</button>
              </div>
            `).join('')}
          </div>
        ` : `<p class="empty">Nenhuma rotina cadastrada ainda. <a href="#rotinas">Criar primeira rotina</a>.</p>`}
      </section>
    </div>
  `;

  bindPushControls();

  $('#month-select').onchange = e => {
    if (!e.target.value) return;
    selectedMonth = e.target.value;
    dashboardView();
  };

  document.querySelectorAll('[data-cal-day]').forEach(btn => {
    btn.onclick = () => openCalendarDay(btn.dataset.calDay);
  });

  document.querySelectorAll('[data-start-routine]').forEach(btn => {
    btn.onclick = async () => {
      if (activeWorkout) {
        location.hash = '#treino';
        return;
      }
      try {
        const w = await api('workouts', 'POST', { routine_id: +btn.dataset.startRoutine });
        activeWorkout = w;
        location.hash = '#treino';
      } catch (err) {
        notify(err.message, 'danger');
      }
    };
  });
}

// ---------------------------------------------------------------------------
// MODAL: Matriz de Estados Temporais do Dia (PONTO 7)
// ---------------------------------------------------------------------------
function renderWorkoutSummaryTable(w) {
  return `
    <table class="exercise-table" style="margin-top:10px;">
      <thead><tr><th>Exercício</th><th>Séries Feitas</th><th>Carga Máx</th></tr></thead>
      <tbody>
        ${w.items.map(it => {
          const doneSets = it.sets.filter(s => s.done);
          const maxLoad = doneSets.length ? Math.max(...doneSets.map(s => s.load)) : 0;
          return `<tr><td>${esc(it.name)}</td><td>${doneSets.length} / ${it.sets.length}</td><td>${maxLoad} kg</td></tr>`;
        }).join('')}
      </tbody>
    </table>
    ${w.notes ? `<p class="muted" style="margin-top:10px;"><small>Notas: ${esc(w.notes)}</small></p>` : ''}
  `;
}

async function openCalendarDay(dateStr) {
  dialogContent.innerHTML = '<p>Carregando estado do dia…</p>';
  dialog.showModal();

  try {
    const [dayData, routines] = await Promise.all([
      api(`calendar/day/${dateStr}`),
      api('routines')
    ]);
    const [y, m, d] = dateStr.split('-');
    const formatted = `${d}/${m}/${y}`;

    let body = `<h2>${formatted}</h2>`;

    if (dayData.state === 'past_trained' && dayData.workout) {
      const w = dayData.workout;
      body += `
        <div class="temporal-card temporal-past-trained">
          <span class="eyebrow" style="color:var(--success);">Treino Realizado</span>
          <h3>${esc(w.routine_name)}</h3>
          <p class="muted"><small>Finalizado às ${w.finished_at ? new Date(w.finished_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : ''}</small></p>
          ${renderWorkoutSummaryTable(w)}
          <div class="actions" style="margin-top:14px;">
            <button type="button" class="danger compact" id="btn-del-workout" data-id="${w.id}">Excluir Registro</button>
          </div>
        </div>
      `;
    } else if (dayData.state === 'past_rest') {
      body += `
        <div class="temporal-card temporal-past-rest">
          <svg style="width:48px;height:48px;fill:none;stroke:var(--muted);stroke-width:1.5;margin-bottom:8px;" viewBox="0 0 24 24"><path d="M20 12V8H6a2 2 0 0 1-2-2c0-1.1.9-2 2-2h12v4"/><path d="M4 6v12c0 1.1.9 2 2 2h14v-4"/><path d="M18 12a2 2 0 0 0-2 2c0 1.1.9 2 2 2h4v-4h-4z"/></svg>
          <h3>Dia de descanso / Nenhum treino realizado</h3>
          <p class="muted">Esta data já passou. Não é permitido criar novos agendamentos no passado.</p>
        </div>
      `;
    } else if (dayData.state === 'today_trained' && dayData.workout) {
      const w = dayData.workout;
      body += `
        <div class="temporal-card temporal-past-trained">
          <span class="eyebrow" style="color:var(--success);">Treino de Hoje Concluído!</span>
          <h3>${esc(w.routine_name)}</h3>
          <p class="muted">Excelente trabalho! O treino de hoje já foi consolidado com sucesso.</p>
          ${renderWorkoutSummaryTable(w)}
          <div class="actions" style="margin-top:14px;">
            <button type="button" class="danger compact" id="btn-del-workout" data-id="${w.id}">Excluir Registro</button>
          </div>
        </div>
      `;
    } else if (dayData.state === 'today_ready') {
      const sched = dayData.schedules && dayData.schedules[0];
      const activeW = dayData.workout && !dayData.workout.finished_at ? dayData.workout : null;
      body += `
        <div class="temporal-card temporal-today-ready">
          <span class="eyebrow" style="color:var(--lime);">${activeW ? 'Treino em Andamento' : 'Treino de Hoje Agendado'}</span>
          <h3>${esc(activeW ? activeW.routine_name : (sched ? sched.routine_name : 'Treino Programado'))}</h3>
          ${sched ? `<p class="muted"><small>Horário agendado: ${sched.scheduled_at.slice(11, 16)}</small></p>` : ''}
          <p>Está na hora de se mover. ${activeW ? 'Retome sua sessão em andamento:' : 'Inicie sua sessão diretamente agora:'}</p>
          <div class="actions" style="margin-top:16px;">
            <button id="btn-start-today" style="width:100%;font-size:16px;padding:14px;">${activeW ? '[ Retomar Treino de Hoje → ]' : '[ Iniciar Treino de Hoje → ]'}</button>
            ${sched && !activeW ? `<button type="button" class="danger compact" id="btn-del-sched" data-id="${sched.id}">Cancelar Agendamento</button>` : ''}
          </div>
        </div>
      `;
    } else {
      // Futuro ou Hoje livre (today_idle, future_scheduled, future_empty)
      body += `
        <div class="temporal-card">
          <h3>${dayData.is_today ? 'Hoje (' + formatted + ')' : 'Agendar Treino para ' + formatted}</h3>
          ${dayData.schedules && dayData.schedules.length ? `
            <div style="margin-bottom:18px;">
              <span class="eyebrow">Agendamento existente:</span>
              <p><strong>${esc(dayData.schedules[0].routine_name)}</strong> às ${dayData.schedules[0].scheduled_at.slice(11, 16)}</p>
              <button class="danger compact" id="btn-del-sched" data-id="${dayData.schedules[0].id}">Excluir Agendamento</button>
            </div>
          ` : routines.length ? `
            <form id="form-schedule" style="margin-top:12px;">
              <label for="sched-routine">Escolha a Rotina:</label>
              <select id="sched-routine" required>
                ${routines.map(r => `<option value="${r.id}">${esc(r.name)}</option>`).join('')}
              </select>
              <label for="sched-time">Horário:</label>
              <input id="sched-time" type="time" value="07:00" required>
              <div class="actions" style="margin-top:16px;">
                <button type="submit">+ Agendar Treino</button>
                ${dayData.is_today ? `<button type="button" class="secondary" id="btn-start-direct">Treinar Agora →</button>` : ''}
              </div>
            </form>
          ` : `<p class="empty">Crie uma rotina primeiro na aba Rotinas para poder agendar.</p>`}
        </div>
      `;
    }

    dialogContent.innerHTML = body;

    const startTodayBtn = $('#btn-start-today');
    if (startTodayBtn) {
      startTodayBtn.onclick = async () => {
        if (dayData.workout && !dayData.workout.finished_at) {
          dialog.close();
          activeWorkout = dayData.workout;
          location.hash = '#treino';
          return;
        }
        const sched = dayData.schedules && dayData.schedules[0];
        try {
          const w = await api('workouts', 'POST', {
            routine_id: sched ? sched.routine_id : routines[0].id,
            schedule_id: sched ? sched.id : undefined
          });
          dialog.close();
          activeWorkout = w;
          location.hash = '#treino';
        } catch (err) {
          notify(err.message, 'danger');
        }
      };
    }

    const startDirectBtn = $('#btn-start-direct');
    if (startDirectBtn) {
      startDirectBtn.onclick = async () => {
        const routineId = +$('#sched-routine').value;
        try {
          const w = await api('workouts', 'POST', { routine_id: routineId });
          dialog.close();
          activeWorkout = w;
          location.hash = '#treino';
        } catch (err) {
          notify(err.message, 'danger');
        }
      };
    }

    const delWorkoutBtn = $('#btn-del-workout');
    if (delWorkoutBtn) {
      delWorkoutBtn.onclick = async () => {
        if (!await confirmAction('Excluir este registro de treino permanentemente?')) return;
        try {
          await api(`workouts/${delWorkoutBtn.dataset.id}`, 'DELETE');
          dialog.close();
          dashboardView();
          notify('Registro de treino excluído.');
        } catch (err) {
          notify(err.message, 'danger');
        }
      };
    }

    const delSchedBtn = $('#btn-del-sched');
    if (delSchedBtn) {
      delSchedBtn.onclick = async () => {
        if (!await confirmAction('Deseja excluir este agendamento?')) return;
        try {
          await api(`schedules/${delSchedBtn.dataset.id}`, 'DELETE');
          dialog.close();
          dashboardView();
          notify('Agendamento excluído.');
        } catch (err) {
          notify(err.message, 'danger');
        }
      };
    }

    const schedForm = $('#form-schedule');
    if (schedForm) {
      schedForm.onsubmit = async e => {
        e.preventDefault();
        const routineId = +$('#sched-routine').value;
        const time = $('#sched-time').value;
        const scheduledAt = `${dateStr}T${time}`;
        try {
          await api('schedules', 'POST', { routine_id: routineId, scheduled_at: scheduledAt });
          dialog.close();
          dashboardView();
          notify('Treino agendado com sucesso!', 'success');
        } catch (err) {
          notify(err.message, 'danger');
        }
      };
    }
  } catch (err) {
    dialogContent.innerHTML = `<p class="danger">${esc(err.message)}</p>`;
  }
}

// ---------------------------------------------------------------------------
// VIEW 2: Rotinas Anatômicas (#rotinas)
// ---------------------------------------------------------------------------
async function routinesView() {
  const routines = await api('routines');

  main.innerHTML = heading('Rotinas de Treino', 'Organize suas sessões por grupos musculares anatômicos.') + `
    <div class="row" style="margin-bottom:20px;">
      <h2>Minhas Fichas</h2>
      <button id="btn-new-routine">+ Nova Rotina</button>
    </div>

    ${routines.length ? `
      <div class="grid">
        ${routines.map(r => `
          <div class="card">
            <div class="row">
              <h3>${esc(r.name)}</h3>
              <span class="badge">${esc(r.target_muscle_groups ? r.target_muscle_groups.split(',').map(m => MUSCLE_LABELS[m] || m).join(', ') : 'Geral')}</span>
            </div>
            <ol class="routine-list">
              ${r.items.map(it => `<li><strong>${esc(it.name)}</strong>: ${it.sets} séries × ${it.reps} reps (descanso ${it.rest}s)</li>`).join('')}
            </ol>
            <div class="actions">
              <button data-start="${r.id}">Treinar Agora</button>
              <button class="secondary compact" data-edit="${r.id}">Editar</button>
              <button class="danger compact" data-delete="${r.id}">Excluir</button>
            </div>
          </div>
        `).join('')}
      </div>
    ` : `<p class="empty">Nenhuma rotina encontrada. Comece criando sua primeira rotina!</p>`}
  `;

  $('#btn-new-routine').onclick = () => openRoutineEditor();

  document.querySelectorAll('[data-start]').forEach(b => {
    b.onclick = async () => {
      try {
        const w = await api('workouts', 'POST', { routine_id: +b.dataset.start });
        activeWorkout = w;
        location.hash = '#treino';
      } catch (err) {
        notify(err.message, 'danger');
      }
    };
  });

  document.querySelectorAll('[data-edit]').forEach(b => {
    b.onclick = () => {
      const routine = routines.find(r => r.id === +b.dataset.edit);
      openRoutineEditor(routine);
    };
  });

  document.querySelectorAll('[data-delete]').forEach(b => {
    b.onclick = async () => {
      if (!await confirmAction('Excluir esta rotina permanentemente?')) return;
      try {
        await api(`routines/${b.dataset.delete}`, 'DELETE');
        routinesView();
        notify('Rotina excluída.');
      } catch (err) {
        notify(err.message, 'danger');
      }
    };
  });
}

// Modal do Editor de Rotinas com Filtro por Chips Anatômicos (PONTO 8 e PONTO 9)
async function openRoutineEditor(existing = null) {
  const exercises = await api('exercises');
  let draftName = existing ? existing.name : '';
  let selectedItems = existing ? JSON.parse(JSON.stringify(existing.items)) : [];
  let selectedMuscles = existing && existing.target_muscle_groups ? existing.target_muscle_groups.split(',').filter(Boolean) : [];

  function syncDraftName() {
    const inp = $('#rot-name');
    if (inp) draftName = inp.value;
  }

  function renderEditor() {
    dialogContent.innerHTML = `
      <h2>${existing ? 'Editar Rotina' : 'Nova Rotina'}</h2>
      <form id="routine-form">
        <label for="rot-name">Nome da Rotina:</label>
        <input id="rot-name" required value="${esc(draftName)}" placeholder="Ex: Treino A - Peito e Tríceps">

        <label>Grupos Musculares Trabalhados:</label>
        <div class="chips">
          ${MUSCLE_ORDER.map(m => `
            <div class="chip ${selectedMuscles.includes(m) ? 'active' : ''}" data-muscle-chip="${m}">
              ${MUSCLE_LABELS[m]}
            </div>
          `).join('')}
        </div>

        <div class="row" style="margin-top:20px;">
          <h3>Exercícios da Rotina (${selectedItems.length})</h3>
          <button type="button" class="secondary compact" id="btn-add-ex">+ Adicionar Exercício</button>
        </div>

        <div id="routine-items-box" style="margin:12px 0;">
          ${selectedItems.length ? selectedItems.map((it, idx) => `
            <div class="editor-item">
              <strong>${idx + 1}. ${esc(it.name)}</strong>
              <div class="fields" style="margin-top:8px;">
                <div><label>Séries</label><input type="number" min="1" max="20" value="${it.sets}" data-item-field="sets" data-idx="${idx}"></div>
                <div><label>Repetições</label><input type="number" min="1" max="1000" value="${it.reps}" data-item-field="reps" data-idx="${idx}"></div>
                <div><label>Descanso (s)</label><input type="number" min="0" max="600" step="5" value="${it.rest}" data-item-field="rest" data-idx="${idx}"></div>
                <div style="display:flex;align-items:flex-end;"><button type="button" class="danger compact" data-remove-item="${idx}">✕</button></div>
              </div>
            </div>
          `).join('') : '<p class="muted"><small>Nenhum exercício adicionado ainda. Clique em "+ Adicionar Exercício".</small></p>'}
        </div>

        <div class="actions" style="margin-top:24px;">
          <button type="submit">Salvar Rotina</button>
        </div>
      </form>
    `;

    $('#rot-name').oninput = e => { draftName = e.target.value; };

    document.querySelectorAll('[data-muscle-chip]').forEach(c => {
      c.onclick = () => {
        syncDraftName();
        const m = c.dataset.muscleChip;
        if (selectedMuscles.includes(m)) {
          selectedMuscles = selectedMuscles.filter(x => x !== m);
        } else {
          selectedMuscles.push(m);
        }
        renderEditor();
      };
    });

    document.querySelectorAll('[data-item-field]').forEach(inp => {
      inp.onchange = () => {
        const idx = +inp.dataset.idx;
        const fld = inp.dataset.itemField;
        selectedItems[idx][fld] = +inp.value;
      };
    });

    document.querySelectorAll('[data-remove-item]').forEach(b => {
      b.onclick = () => {
        syncDraftName();
        selectedItems.splice(+b.dataset.removeItem, 1);
        renderEditor();
      };
    });

    $('#btn-add-ex').onclick = () => {
      syncDraftName();
      openExerciseSelector(exercises, item => {
        if (item) {
          selectedItems.push({
            exercise_id: item.id,
            name: item.name,
            muscle_group: item.muscle_group,
            sets: 3,
            reps: 10,
            rest: 90
          });
          if (item.muscle_group && !selectedMuscles.includes(item.muscle_group)) {
            selectedMuscles.push(item.muscle_group);
          }
        }
        renderEditor();
      });
    };

    $('#routine-form').onsubmit = async e => {
      e.preventDefault();
      const name = $('#rot-name').value.trim();
      if (!selectedItems.length) {
        notify('Adicione pelo menos um exercício à rotina.', 'danger');
        return;
      }
      const payload = {
        name,
        target_muscle_groups: selectedMuscles.join(','),
        items: selectedItems
      };
      try {
        if (existing) {
          await api(`routines/${existing.id}`, 'PUT', payload);
        } else {
          await api('routines', 'POST', payload);
        }
        dialog.close();
        routinesView();
        notify('Rotina salva com sucesso!', 'success');
      } catch (err) {
        notify(err.message, 'danger');
      }
    };
  }

  renderEditor();
  dialog.showModal();
}

// Sub-modal seletor de exercícios com Chips Anatômicos e Busca Reativa sem perda de foco (PONTO 8)
function openExerciseSelector(allExercises, onSelect) {
  let activeFilter = 'todos';
  let searchTerm = '';

  dialogContent.innerHTML = `
    <h3>Selecionar Exercício</h3>
    <div class="chips" id="picker-chips"></div>
    <input id="picker-search" type="search" placeholder="Filtrar por nome do exercício..." style="margin:10px 0;">
    <div id="picker-results" style="max-height:300px;overflow-y:auto;border:1px solid var(--line);border-radius:10px;padding:8px;"></div>
    <div class="actions" style="margin-top:16px;">
      <button type="button" class="secondary" id="btn-cancel-picker">← Voltar para a Rotina</button>
    </div>
  `;

  function updateChips() {
    $('#picker-chips').innerHTML = `
      <div class="chip ${activeFilter === 'todos' ? 'active' : ''}" data-picker-chip="todos">Todos</div>
      ${MUSCLE_ORDER.map(m => `
        <div class="chip ${activeFilter === m ? 'active' : ''}" data-picker-chip="${m}">${MUSCLE_LABELS[m]}</div>
      `).join('')}
    `;
    document.querySelectorAll('[data-picker-chip]').forEach(c => {
      c.onclick = () => {
        activeFilter = c.dataset.pickerChip;
        updateChips();
        updateResults();
      };
    });
  }

  function updateResults() {
    const q = normalizeSearch(searchTerm);
    const filtered = allExercises.filter(ex => {
      const matchMuscle = (activeFilter === 'todos') || (ex.muscle_group === activeFilter);
      const matchSearch = !q || normalizeSearch(ex.name).includes(q);
      return matchMuscle && matchSearch;
    });

    const box = $('#picker-results');
    box.innerHTML = filtered.length ? filtered.map(ex => `
      <div class="session-row row" style="padding:8px;">
        <div>
          <strong>${esc(ex.name)}</strong>
          <span class="badge" style="margin-left:8px;font-size:11px;">${MUSCLE_LABELS[ex.muscle_group] || ex.muscle_group}</span>
        </div>
        <button type="button" class="compact" data-pick-id="${ex.id}">Escolher</button>
      </div>
    `).join('') : '<p class="empty">Nenhum exercício encontrado com esses filtros.</p>';

    box.querySelectorAll('[data-pick-id]').forEach(b => {
      b.onclick = () => {
        const item = allExercises.find(x => x.id === +b.dataset.pickId);
        onSelect(item);
      };
    });
  }

  updateChips();
  updateResults();

  const searchInp = $('#picker-search');
  searchInp.oninput = () => {
    searchTerm = searchInp.value;
    updateResults();
  };

  $('#btn-cancel-picker').onclick = () => onSelect(null);
}

// ---------------------------------------------------------------------------
// VIEW 3: Treino em Execução (#treino)
// ---------------------------------------------------------------------------
async function workoutView() {
  const active = await api('workouts/active');
  activeWorkout = active;

  if (!active) {
    const routines = await api('routines');
    main.innerHTML = heading('Execução de Treino', 'Escolha uma rotina abaixo para iniciar sua sessão.') + `
      ${routines.length ? `
        <div class="grid">
          ${routines.map(r => `
            <div class="card">
              <div class="row">
                <h3>${esc(r.name)}</h3>
                <span class="badge">${esc(r.target_muscle_groups ? r.target_muscle_groups.split(',').map(m => MUSCLE_LABELS[m] || m).join(', ') : 'Geral')}</span>
              </div>
              <ol class="routine-list">
                ${r.items.map(it => `<li>${esc(it.name)} <small>· ${it.sets} × ${it.reps} · ${it.rest}s</small></li>`).join('')}
              </ol>
              <button data-start-workout="${r.id}">Iniciar Treino →</button>
            </div>
          `).join('')}
        </div>
      ` : `
        <section class="card" style="text-align:center;padding:40px 20px;">
          <p>Você ainda não possui rotinas cadastradas.</p>
          <a class="button" href="#rotinas">Criar Primeira Rotina →</a>
        </section>
      `}
    `;
    document.querySelectorAll('[data-start-workout]').forEach(b => {
      b.onclick = async () => {
        try {
          activeWorkout = await api('workouts', 'POST', { routine_id: +b.dataset.startWorkout });
          workoutView();
        } catch (err) {
          notify(err.message, 'danger');
        }
      };
    });
    return;
  }

  const w = active;
  main.innerHTML = heading('Treino Ativo: ' + w.routine_name, 'As cargas anteriores já foram pré-preenchidas. Marque cada série concluída.') + `
    <div class="row" style="margin-bottom:18px;">
      <span class="muted" id="save-state" role="status">Iniciado às ${new Date(w.started_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</span>
      <div class="actions">
        <button class="danger compact" id="btn-discard-workout">Descartar Treino</button>
        <button id="finish" style="font-size:15px;padding:12px 24px;">Finalizar Treino ✓</button>
      </div>
    </div>

    <div id="workout-items-container">
      ${w.items.map((it, itemIdx) => `
        <div class="card" data-workout-item="${it.id}">
          <div class="row">
            <h3>${it.position + 1}. ${esc(it.name)}</h3>
            <button class="secondary compact" data-rest-timer="${it.rest}">Descanso (${it.rest}s)</button>
          </div>
          
          <div class="set-row set-head">
            <span>Série</span>
            <span>Reps</span>
            <span>Carga (kg)</span>
            <span>Feito</span>
          </div>

          ${it.sets.map((s, setIdx) => `
            <div class="set-row" data-set-id="${s.id}">
              <span>#${s.position + 1}</span>
              <input type="number" inputmode="numeric" min="0" max="1000" value="${s.reps}" data-set-field="reps" data-item="${itemIdx}" data-set="${setIdx}" aria-label="Repetições da série ${s.position + 1}">
              <input type="number" inputmode="decimal" step="0.5" min="0" max="9999" value="${s.load}" data-set-field="load" data-item="${itemIdx}" data-set="${setIdx}" aria-label="Carga da série ${s.position + 1}">
              <div style="display:flex;justify-content:center;">
                <input type="checkbox" ${s.done ? 'checked' : ''} data-set-field="done" data-item="${itemIdx}" data-set="${setIdx}" aria-label="Série ${s.position + 1} concluída">
              </div>
            </div>
          `).join('')}

          <input placeholder="Observações deste exercício (opcional)..." value="${esc(it.notes || '')}" data-item-notes="${itemIdx}" style="margin-top:12px;font-size:13px;">
        </div>
      `).join('')}
    </div>

    <section class="card" style="margin-top:24px;">
      <label for="workout-general-notes">Anotações Gerais da Sessão:</label>
      <textarea id="workout-general-notes" placeholder="Como foi o treino, energia, sensações...">${esc(w.notes || '')}</textarea>
    </section>
  `;

  document.querySelectorAll('[data-rest-timer]').forEach(b => {
    b.onclick = () => startTimer(+b.dataset.restTimer);
  });

  let savePromise = Promise.resolve();
  let saveDebounce = null;

  async function saveNow(finish = false) {
    clearTimeout(saveDebounce);
    const stateEl = $('#save-state');
    if (stateEl) stateEl.textContent = 'Salvando alterações…';
    const payload = {
      notes: w.notes,
      items: w.items,
      finish
    };
    savePromise = api(`workouts/${w.id}`, 'PUT', payload).then(updated => {
      if (stateEl) {
        stateEl.textContent = 'Alterações salvas automaticamente ✓';
        stateEl.dataset.kind = 'success';
      }
      return updated;
    });
    return savePromise;
  }

  function triggerAutoSave() {
    clearTimeout(saveDebounce);
    saveDebounce = setTimeout(() => {
      saveNow(false).catch(err => console.error('Falha no auto-save:', err));
    }, 450);
  }

  document.querySelectorAll('[data-set-field]').forEach(input => {
    const handler = () => {
      const itIdx = +input.dataset.item;
      const stIdx = +input.dataset.set;
      const fld = input.dataset.setField;
      if (fld === 'done') {
        w.items[itIdx].sets[stIdx].done = input.checked;
        if (input.checked) {
          startTimer(w.items[itIdx].rest);
        }
      } else if (fld === 'reps') {
        w.items[itIdx].sets[stIdx].reps = Math.max(0, parseInt(input.value, 10) || 0);
      } else if (fld === 'load') {
        w.items[itIdx].sets[stIdx].load = Math.max(0, parseFloat(input.value) || 0);
      }
      triggerAutoSave();
    };
    input.onchange = handler;
    if (input.type !== 'checkbox') input.oninput = handler;
  });

  document.querySelectorAll('[data-item-notes]').forEach(inp => {
    inp.oninput = () => {
      w.items[+inp.dataset.itemNotes].notes = inp.value;
      triggerAutoSave();
    };
  });

  $('#workout-general-notes').oninput = e => {
    w.notes = e.target.value;
    triggerAutoSave();
  };

  $('#finish').onclick = async () => {
    if (!w.items.some(it => it.sets.some(s => s.done))) {
      notify('Marque pelo menos uma série como concluída antes de finalizar.', 'danger');
      return;
    }
    if (!await confirmAction('Deseja concluir e salvar este treino no histórico?')) return;
    try {
      await saveNow(true);
      activeWorkout = null;
      stopTimer();
      notify('Treino concluído com sucesso! Bom descanso.', 'success');
      location.hash = '#inicio';
    } catch (err) {
      notify(err.message, 'danger');
    }
  };

  $('#btn-discard-workout').onclick = async () => {
    if (!await confirmAction('Atenção: Descartar este treino apagará os dados desta sessão. Confirmar?')) return;
    try {
      clearTimeout(saveDebounce);
      await api(`workouts/${w.id}`, 'DELETE');
      activeWorkout = null;
      stopTimer();
      notify('Treino descartado.');
      location.hash = '#inicio';
    } catch (err) {
      notify(err.message, 'danger');
    }
  };
}

// ---------------------------------------------------------------------------
// VIEW 4: Biometria e Fotos de Evolução Física (#biometria) (PONTO 2 e PONTO 4)
// ---------------------------------------------------------------------------
async function biometricsView() {
  const [metrics, photos] = await Promise.all([
    api('metrics/weight'),
    api('evolution/photos')
  ]);

  main.innerHTML = heading('Evolução Física & Biometria', 'Acompanhamento soberano de peso corporal e fotos de progresso.') + `
    <!-- PONTO 6: Sem barras de pesquisa redundantes nesta aba -->
    <div class="grid">
      <!-- Módulo 1: Peso Corporal (PONTO 4) -->
      <section class="card">
        <h2>Registro de Peso Corporal</h2>
        <form id="weight-form" style="margin-bottom:20px;">
          <div class="fields" style="grid-template-columns:1fr 1fr auto;">
            <div>
              <label for="weight-val">Peso (kg):</label>
              <input id="weight-val" type="number" step="0.1" min="20" max="500" required placeholder="Ex: 65.5">
            </div>
            <div>
              <label for="weight-date">Data:</label>
              <input id="weight-date" type="date" value="${localTodayStr()}" required>
            </div>
            <div style="display:flex;align-items:flex-end;">
              <button type="submit">Salvar</button>
            </div>
          </div>
          <input id="weight-notes" placeholder="Notas sobre a pesagem (opcional)..." style="margin-top:10px;font-size:13px;">
        </form>

        ${renderWeightSvg(metrics)}

        <h3 style="margin-top:24px;">Histórico de Medições</h3>
        ${metrics.length ? `
          <table class="exercise-table">
            <thead><tr><th>Data</th><th>Peso</th><th>Variação</th><th>Notas</th><th></th></tr></thead>
            <tbody>
              ${metrics.map(m => {
                const deltaStr = m.delta > 0 ? `+${m.delta.toFixed(2)} kg` : m.delta < 0 ? `${m.delta.toFixed(2)} kg` : '= 0.0 kg';
                const deltaClass = m.delta > 0 ? 'delta-pos' : m.delta < 0 ? 'delta-neg' : 'delta-zero';
                return `
                  <tr>
                    <td>${m.recorded_at.split('-').reverse().join('/')}</td>
                    <td><strong>${m.weight.toFixed(1)} kg</strong></td>
                    <td><span class="delta-badge ${deltaClass}">${deltaStr}</span></td>
                    <td class="muted"><small>${esc(m.notes || '—')}</small></td>
                    <td><button class="danger compact" data-del-weight="${m.id}">✕</button></td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        ` : `<p class="empty">Nenhuma pesagem cadastrada. Registre seu primeiro peso acima.</p>`}
      </section>

      <!-- Módulo 2: Galeria de Fotos de Evolução (PONTO 2) -->
      <section class="card">
        <div class="row">
          <h2>Galeria de Fotos</h2>
          <button id="btn-upload-photo">+ Nova Foto</button>
        </div>
        <p class="muted"><small>Pipeline WebP automático: compressão local para 1080px (80% qualidade) para economia de espaço.</small></p>

        ${photos.length ? `
          <div class="photo-grid">
            ${photos.map(p => `
              <div class="photo-card">
                <span class="photo-angle-tag">${esc(p.angle)}</span>
                <img src="${esc(p.photo_path)}" alt="Foto de evolução (${esc(p.angle)})" loading="lazy" data-view-photo="${esc(p.photo_path)}" style="cursor:pointer;">
                <div class="photo-card-info">
                  <span class="muted">${p.taken_at.split('-').reverse().join('/')}</span>
                  <button class="photo-delete" data-del-photo="${p.id}" title="Excluir foto">✕</button>
                </div>
              </div>
            `).join('')}
          </div>
        ` : `<p class="empty">Nenhuma foto adicionada ainda. Adicione fotos para acompanhar sua transformação.</p>`}
      </section>
    </div>
  `;

  $('#weight-form').onsubmit = async e => {
    e.preventDefault();
    const weight = parseFloat($('#weight-val').value);
    const recorded_at = $('#weight-date').value;
    const notes = $('#weight-notes').value.trim();
    try {
      await api('metrics/weight', 'POST', { weight, recorded_at, notes });
      notify('Peso registrado com sucesso!', 'success');
      biometricsView();
    } catch (err) {
      notify(err.message, 'danger');
    }
  };

  document.querySelectorAll('[data-del-weight]').forEach(b => {
    b.onclick = async () => {
      if (!await confirmAction('Excluir este registro de peso?')) return;
      try {
        await api(`metrics/weight/${b.dataset.delWeight}`, 'DELETE');
        biometricsView();
        notify('Registro excluído.');
      } catch (err) {
        notify(err.message, 'danger');
      }
    };
  });

  $('#btn-upload-photo').onclick = () => openPhotoUploader();

  document.querySelectorAll('[data-view-photo]').forEach(img => {
    img.onclick = () => {
      dialogContent.innerHTML = `<div style="text-align:center;"><img src="${esc(img.dataset.viewPhoto)}" style="max-width:100%;max-height:75vh;border-radius:12px;"></div>`;
      dialog.showModal();
    };
  });

  document.querySelectorAll('[data-del-photo]').forEach(b => {
    b.onclick = async () => {
      if (!await confirmAction('Excluir esta foto da galeria?')) return;
      try {
        await api(`evolution/photos/${b.dataset.delPhoto}`, 'DELETE');
        biometricsView();
        notify('Foto removida.');
      } catch (err) {
        notify(err.message, 'danger');
      }
    };
  });
}

// Modal de Upload com Compressão Canvas WebP (PONTO 2)
function openPhotoUploader() {
  dialogContent.innerHTML = `
    <h2>Adicionar Foto de Evolução</h2>
    <form id="photo-upload-form">
      <label for="photo-file">Selecione ou Tire a Foto:</label>
      <input type="file" id="photo-file" accept="image/*" required>

      <label for="photo-angle">Ângulo da Foto:</label>
      <select id="photo-angle">
        <option value="frontal">Frontal</option>
        <option value="costas">Costas</option>
        <option value="lateral">Lateral</option>
        <option value="outro">Outro / Detalhe</option>
      </select>

      <label for="photo-date">Data da Foto:</label>
      <input type="date" id="photo-date" value="${localTodayStr()}" required>

      <div id="photo-preview-box" style="margin:16px 0;text-align:center;"></div>

      <div class="actions" style="margin-top:20px;">
        <button type="submit" id="btn-submit-photo">Comprimir e Enviar</button>
      </div>
    </form>
  `;

  let compressedBlob = null;
  const fileInput = $('#photo-file');
  const previewBox = $('#photo-preview-box');

  fileInput.onchange = () => {
    const file = fileInput.files[0];
    if (!file) return;

    previewBox.innerHTML = '<p class="muted">Comprimindo imagem localmente...</p>';

    const reader = new FileReader();
    reader.onload = e => {
      const img = new Image();
      img.onload = () => {
        const maxW = 1080;
        let w = img.width;
        let h = img.height;
        if (w > maxW) {
          h = Math.round(h * (maxW / w));
          w = maxW;
        }
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, w, h);

        canvas.toBlob(blob => {
          compressedBlob = blob;
          const url = URL.createObjectURL(blob);
          previewBox.innerHTML = `
            <img src="${url}" style="max-height:220px;border-radius:10px;display:inline-block;border:1px solid var(--line);">
            <p class="muted"><small>Tamanho final: ${(blob.size / 1024).toFixed(0)} KB (WebP)</small></p>
          `;
        }, 'image/webp', 0.8);
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  };

  $('#photo-upload-form').onsubmit = async e => {
    e.preventDefault();
    if (!compressedBlob && !fileInput.files[0]) {
      notify('Selecione uma foto.', 'danger');
      return;
    }

    const submitBtn = $('#btn-submit-photo');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Enviando...';

    const formData = new FormData();
    const finalFile = compressedBlob || fileInput.files[0];
    formData.append('photo', finalFile, 'photo.webp');
    formData.append('angle', $('#photo-angle').value);
    formData.append('taken_at', $('#photo-date').value);
    formData.append('csrf_token', csrfToken);

    try {
      await api('evolution/photos', 'POST', formData, true);
      dialog.close();
      biometricsView();
      notify('Foto enviada e adicionada à galeria!', 'success');
    } catch (err) {
      notify(err.message, 'danger');
      submitBtn.disabled = false;
      submitBtn.textContent = 'Comprimir e Enviar';
    }
  };

  dialog.showModal();
}

// ---------------------------------------------------------------------------
// VIEW 5: Catálogo de Exercícios com Chips e Busca (#exercicios) (PONTO 8)
// ---------------------------------------------------------------------------
async function exercisesView() {
  const exercises = await api('exercises');
  let activeMuscle = 'todos';
  let searchTerm = '';

  main.innerHTML = heading('Catálogo Anatômico de Exercícios', 'Classificação direta por grupos musculares.') + `
    <div class="row" style="margin-bottom:14px;">
      <h2 id="catalog-count">Exercícios (${exercises.length})</h2>
      <button id="btn-new-exercise">+ Novo Exercício</button>
    </div>

    <!-- Filtro por Chips Anatômicos (PONTO 8) -->
    <div class="chips" id="catalog-chips"></div>

    <!-- PONTO 6: Busca permitida nesta aba de catálogo (sem perda de foco) -->
    <input id="catalog-search" type="search" placeholder="Buscar por nome do exercício..." style="margin:16px 0;">

    <div id="catalog-table-box"></div>
  `;

  function updateChips() {
    $('#catalog-chips').innerHTML = `
      <div class="chip ${activeMuscle === 'todos' ? 'active' : ''}" data-muscle-filter="todos">Todos</div>
      ${MUSCLE_ORDER.map(m => `
        <div class="chip ${activeMuscle === m ? 'active' : ''}" data-muscle-filter="${m}">${MUSCLE_LABELS[m]}</div>
      `).join('')}
    `;
    document.querySelectorAll('[data-muscle-filter]').forEach(c => {
      c.onclick = () => {
        activeMuscle = c.dataset.muscleFilter;
        updateChips();
        updateTable();
      };
    });
  }

  function updateTable() {
    const q = normalizeSearch(searchTerm);
    const filtered = exercises.filter(e => {
      const matchM = (activeMuscle === 'todos') || (e.muscle_group === activeMuscle);
      const matchS = !q || normalizeSearch(e.name).includes(q);
      return matchM && matchS;
    });

    $('#catalog-count').textContent = `Exercícios (${filtered.length})`;
    const box = $('#catalog-table-box');
    box.innerHTML = filtered.length ? `
      <table class="exercise-table">
        <thead><tr><th>Exercício</th><th>Grupo Muscular</th><th>Equipamento</th><th>Ações</th></tr></thead>
        <tbody>
          ${filtered.map(ex => `
            <tr>
              <td><strong>${esc(ex.name)}</strong> ${ex.custom ? '<span class="badge" style="font-size:10px;">Seu</span>' : ''}</td>
              <td><span class="badge">${MUSCLE_LABELS[ex.muscle_group] || ex.muscle_group}</span></td>
              <td class="muted"><small>${esc(ex.equipment || '—')}</small></td>
              <td>
                <div class="actions">
                  <button class="secondary compact" data-edit-ex="${ex.id}">Editar</button>
                  ${ex.custom ? `<button class="danger compact" data-del-ex="${ex.id}">✕</button>` : ''}
                </div>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    ` : `<p class="empty">Nenhum exercício encontrado com esses filtros.</p>`;

    box.querySelectorAll('[data-edit-ex]').forEach(b => {
      b.onclick = () => {
        const ex = exercises.find(x => x.id === +b.dataset.editEx);
        openExerciseEditor(ex);
      };
    });

    box.querySelectorAll('[data-del-ex]').forEach(b => {
      b.onclick = async () => {
        if (!await confirmAction('Excluir este exercício customizado?')) return;
        try {
          await api(`exercises/${b.dataset.delEx}`, 'DELETE');
          exercisesView();
          notify('Exercício excluído.');
        } catch (err) {
          notify(err.message, 'danger');
        }
      };
    });
  }

  updateChips();
  updateTable();

  const searchInp = $('#catalog-search');
  searchInp.oninput = () => {
    searchTerm = searchInp.value;
    updateTable();
  };

  $('#btn-new-exercise').onclick = () => openExerciseEditor();
}

function openExerciseEditor(existing = null) {
  dialogContent.innerHTML = `
    <h2>${existing ? 'Editar Exercício' : 'Novo Exercício'}</h2>
    <form id="ex-form">
      <label for="ex-name">Nome do Exercício:</label>
      <input id="ex-name" required value="${existing ? esc(existing.name) : ''}" placeholder="Ex: Supino Inclinado com Halteres">

      <label for="ex-muscle">Grupo Muscular Principal:</label>
      <select id="ex-muscle">
        ${MUSCLE_ORDER.map(m => `
          <option value="${m}" ${existing && existing.muscle_group === m ? 'selected' : ''}>${MUSCLE_LABELS[m]}</option>
        `).join('')}
      </select>

      <label for="ex-equip">Equipamento (opcional):</label>
      <input id="ex-equip" value="${existing ? esc(existing.equipment || '') : ''}" placeholder="Ex: Halteres, Barra, Máquina">

      <div class="actions" style="margin-top:20px;">
        <button type="submit">Salvar Exercício</button>
      </div>
    </form>
  `;

  $('#ex-form').onsubmit = async e => {
    e.preventDefault();
    const payload = {
      name: $('#ex-name').value.trim(),
      muscle_group: $('#ex-muscle').value,
      equipment: $('#ex-equip').value.trim()
    };
    try {
      if (existing) {
        await api(`exercises/${existing.id}`, 'PUT', payload);
      } else {
        await api('exercises', 'POST', payload);
      }
      dialog.close();
      exercisesView();
      notify('Exercício salvo com sucesso!', 'success');
    } catch (err) {
      notify(err.message, 'danger');
    }
  };

  dialog.showModal();
}

// ---------------------------------------------------------------------------
// VIEW 6: Histórico de Séries e Cargas (#historico) (PONTO 6)
// ---------------------------------------------------------------------------
async function historyView() {
  const exercises = await api('exercises');
  let selectedExerciseId = exercises.length ? exercises[0].id : null;

  async function loadHistoryFor(exId) {
    const histBox = $('#history-details-box');
    if (!exId) {
      histBox.innerHTML = '<p class="empty">Selecione um exercício acima.</p>';
      return;
    }
    const records = await api(`history/${exId}`);
    const ex = exercises.find(x => x.id === exId);

    if (!records.length) {
      histBox.innerHTML = `<div class="card"><p class="empty">Nenhuma série concluída registrada para <strong>${esc(ex ? ex.name : '')}</strong> ainda.</p></div>`;
      return;
    }

    // Maior carga por data para o gráfico SVG
    const byDate = {};
    records.forEach(r => {
      const d = r.date.slice(0, 10);
      byDate[d] = Math.max(byDate[d] ?? 0, r.load);
    });
    const points = Object.entries(byDate);
    const maxLoad = Math.max(1, ...points.map(p => p[1]));
    const x = i => 50 + (points.length === 1 ? 260 : (i * 500) / (points.length - 1));
    const y = v => 180 - (v * 135) / maxLoad;

    const fmtDate = dStr => dStr.slice(0, 10).split('-').reverse().join('/');

    histBox.innerHTML = `
      <div class="card">
        <h3>Progressão de Carga: ${esc(ex ? ex.name : '')}</h3>
        <p class="muted"><small>Maior carga registrada por sessão (kg).</small></p>
        <svg class="chart" viewBox="0 0 600 220" role="img" aria-label="Gráfico de progressão de carga">
          <line x1="50" y1="180" x2="560" y2="180"/>
          <line x1="50" y1="45" x2="560" y2="45"/>
          <text x="8" y="180">0 kg</text>
          <text x="8" y="45">${maxLoad} kg</text>
          <polyline points="${points.map((p, i) => `${x(i)},${y(p[1])}`).join(' ')}"/>
          ${points.map((p, i) => `<circle cx="${x(i)}" cy="${y(p[1])}" r="4.5"><title>${fmtDate(p[0])}: ${p[1]} kg</title></circle>`).join('')}
          <text x="50" y="208">${fmtDate(points[0][0])}</text>
          <text x="555" y="208" text-anchor="end">${fmtDate(points.at(-1)[0])}</text>
        </svg>

        <table class="exercise-table" style="margin-top:16px;">
          <thead><tr><th>Data</th><th>Carga</th><th>Repetições</th></tr></thead>
          <tbody>
            ${[...records].reverse().map(r => `
              <tr>
                <td>${fmtDate(r.date)}</td>
                <td><strong>${r.load} kg</strong></td>
                <td>${r.reps} reps</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  main.innerHTML = heading('Histórico de Cargas', 'Acompanhe a progressão detalhada por exercício.') + `
    <!-- PONTO 6: Busca permitida nesta aba de Histórico -->
    <div class="card">
      <label for="history-search">Buscar Exercício no Histórico:</label>
      <input id="history-search" type="search" placeholder="Digite para filtrar exercícios..." style="margin-bottom:10px;">
      <label for="history-ex-select">Exercício Selecionado:</label>
      <select id="history-ex-select"></select>
    </div>

    <div id="history-details-box"></div>
  `;

  const searchInp = $('#history-search');
  const sel = $('#history-ex-select');

  function populateSelect(filterText = '') {
    const q = normalizeSearch(filterText);
    const matches = exercises.filter(e => !q || normalizeSearch(e.name).includes(q) || normalizeSearch(MUSCLE_LABELS[e.muscle_group] || '').includes(q));
    sel.innerHTML = matches.length
      ? matches.map(e => `<option value="${e.id}" ${e.id === selectedExerciseId ? 'selected' : ''}>${esc(e.name)} (${MUSCLE_LABELS[e.muscle_group] || e.muscle_group})</option>`).join('')
      : '<option value="">Nenhum exercício encontrado</option>';
    if (matches.length && !matches.some(e => e.id === selectedExerciseId)) {
      selectedExerciseId = matches[0].id;
      sel.value = String(selectedExerciseId);
      loadHistoryFor(selectedExerciseId);
    } else if (!matches.length) {
      loadHistoryFor(null);
    }
  }

  searchInp.oninput = () => populateSelect(searchInp.value);
  sel.onchange = () => {
    selectedExerciseId = +sel.value;
    loadHistoryFor(selectedExerciseId);
  };

  populateSelect('');
  if (selectedExerciseId) loadHistoryFor(selectedExerciseId);
}

// ---------------------------------------------------------------------------
// Router Principal (SPA)
// ---------------------------------------------------------------------------
function router() {
  const hash = location.hash || '#inicio';
  document.querySelectorAll('nav a').forEach(a => {
    a.classList.toggle('active', a.getAttribute('href') === hash);
  });

  if (hash === '#rotinas') {
    routinesView();
  } else if (hash === '#treino') {
    workoutView();
  } else if (hash === '#biometria') {
    biometricsView();
  } else if (hash === '#exercicios') {
    exercisesView();
  } else if (hash === '#historico') {
    historyView();
  } else {
    dashboardView();
  }
}

// ---------------------------------------------------------------------------
// Inicialização do App (PONTO 1: Bypass de Senha e Inicialização Transparente)
// ---------------------------------------------------------------------------
async function boot() {
  $('#close-dialog').onclick = () => dialog.close();
  initTimer();

  try {
    const authData = await api('auth');
    csrfToken = authData.csrf;
  } catch (err) {
    console.error('Falha na inicialização da autenticação:', err);
  }

  window.addEventListener('hashchange', router);
  router();
}

boot();

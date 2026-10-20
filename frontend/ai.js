'use strict';
// Rascunhos e formulário ficam somente na memória desta página.
let aiDrafts=[];
$('#dialog').addEventListener('close',()=>{aiDrafts=[];if($('#ai-form')||$('#ai-review-form'))$('#dialog-content').replaceChildren();});
$('#logout').addEventListener('click',()=>{aiDrafts=[]});
async function aiSuggestion(){
  const status=await api('ai/settings');
  aiDrafts=[];
  openModal(`<h2>Rascunhos com Gemini</h2><p class="muted">Opcional. As rotinas e exercícios manuais continuam disponíveis.</p>
    <p id="ai-status" role="status">${status.configured?'Gemini gratuito configurado.':'Gemini não configurado no servidor para um projeto gratuito.'}</p>
    <label class="check-label"><input id="ai-enabled" type="checkbox" ${status.enabled?'checked':''}> Habilitar integração com Google Gemini</label>
    <form id="ai-form"><label>Objetivo<select id="ai-goal">${goalOptions('hipertrofia')}</select></label>
    <label>Experiência<select id="ai-experience"><option>iniciante</option><option>intermediário</option><option>avançado</option></select></label>
    <div class="fields"><label>Dias por semana<input id="ai-days" type="number" min="1" max="6" value="3" required></label><label>Minutos por sessão<input id="ai-minutes" type="number" min="15" max="120" value="45" required></label></div>
    <label>Equipamentos disponíveis<textarea id="ai-equipment" maxlength="500" placeholder="Ex.: halteres, banco, elásticos" required></textarea></label>
    <label>Limitações ou movimentos que precisa evitar<textarea id="ai-limitations" maxlength="500" placeholder="Opcional. Não solicite diagnóstico ou tratamento."></textarea></label>
    <div class="fields"><label>Peso (kg), opcional<input id="ai-weight" type="number" min="20" max="500" step="0.1"></label><label>Altura (cm), opcional<input id="ai-height" type="number" min="80" max="250" step="0.1"></label></div>
    <section class="card ai-notice"><h3>Antes de enviar à Google</h3><p>Serão enviados somente os campos deste formulário: objetivo, experiência, dias, duração, equipamentos, limitações e peso/altura, se preenchidos. Não enviaremos sua senha, catálogo, histórico, cargas ou observações dos treinos.</p><p>No nível gratuito, a Google pode usar os dados para melhorar seus produtos. Evite informações que não deseja compartilhar. Desmarque a integração acima para impedir novos envios.</p><p>A IA não avalia lesões nem prescreve tratamento e não recomenda aumento de carga. Revise os rascunhos antes de usar.</p>
    <label class="check-label"><input id="ai-consent" type="checkbox" required> Autorizo enviar estes campos à Google para esta geração.</label></section>
    <button id="ai-generate" ${!status.configured||!status.enabled?'disabled':''}>Enviar à Google e gerar rascunhos</button><p id="ai-error" class="muted" role="status"></p></form><div id="ai-results"></div>`);
  let enabled=status.enabled, pending=false;
  $('#ai-enabled').onchange=async e=>{
    const checkbox=e.target;checkbox.disabled=true;
    try{const result=await api('ai/settings','PUT',{enabled:checkbox.checked});enabled=result.enabled;
      $('#ai-generate').disabled=!enabled||!status.configured||pending;
      $('#ai-status').textContent=!enabled?'Integração desativada. Nenhum novo dado será enviado.':status.configured?'Integração habilitada. O envio exige autorização abaixo.':'Gemini não configurado no servidor. Use os recursos manuais.';
      if(!enabled){aiDrafts=[];$('#ai-results').replaceChildren();$('#ai-consent').checked=false;}
    }catch(error){checkbox.checked=enabled;$('#ai-error').textContent=error.message;}finally{checkbox.disabled=false;}
  };
  $('#ai-form').onsubmit=async e=>{
    e.preventDefault(); if(pending||!enabled)return;
    const button=$('#ai-generate'), errorBox=$('#ai-error'), results=$('#ai-results');
    const profile={goal:$('#ai-goal').value,experience:$('#ai-experience').value,days:+$('#ai-days').value,minutes:+$('#ai-minutes').value,equipment:$('#ai-equipment').value,limitations:$('#ai-limitations').value,consent:$('#ai-consent').checked};
    for(const field of ['weight','height'])if($('#ai-'+field).value)profile[field]=+$('#ai-'+field).value;
    pending=true;button.disabled=true;button.textContent='Gerando rascunhos…';errorBox.textContent='';aiDrafts=[];results.replaceChildren();
    try{const result=await api('ai/suggest','POST',profile);
      if(!enabled||!button.isConnected)return;
      aiDrafts=result.routines;results.innerHTML=`<h2>Revise antes de salvar</h2><p class="muted">${esc(result.note)}</p>${searchBox('Buscar rotina ou exercício nos rascunhos','[data-ai-draft]')}${aiDrafts.map((r,i)=>`<article class="card" data-ai-draft data-search-names="${searchNames([r.name,...r.items.map(i=>i.name)])}"><span class="badge">Rascunho · nada salvo</span><h3>${esc(r.name)}</h3><ul class="routine-list">${r.items.map(item=>`<li>${esc(item.name)} · ${item.sets} × ${item.reps} · ${item.rest}s<br><small>${item.existing_id?'Usará o exercício existente: '+esc(item.existing_name):'Novo exercício proposto'}</small></li>`).join('')}</ul><button data-ai-review="${i}" class="secondary" type="button">Revisar exercícios e rotina</button></article>`).join('')}`;
      bindNameSearch(dialog);document.querySelectorAll('[data-ai-review]').forEach(b=>b.onclick=()=>aiReview(aiDrafts[+b.dataset.aiReview]));
    }catch(error){if(errorBox.isConnected)errorBox.textContent=error.message;}
    finally{pending=false;if(button.isConnected){button.disabled=!enabled||!status.configured;button.textContent='Enviar à Google e gerar rascunhos';$('#ai-consent').checked=false;}}
  };
}
function aiReview(r){
  const muscles=['Peito','Costas','Pernas','Ombros','Braços','Abdômen','Condicionamento','Corpo inteiro'];
  openModal(`<h2>Revisar rascunho</h2><p class="muted">Edite ou remova exercícios. Nada será salvo até sua confirmação. Nomes equivalentes reutilizam o catálogo existente.</p>
    <form id="ai-review-form"><label>Nome da rotina<input id="ai-name" value="${esc(r.name)}" maxlength="100" required></label><label>Objetivo<select id="ai-review-goal">${goalOptions(r.goal)}</select></label>
    ${searchBox('Buscar exercício no rascunho','.ai-item')}<div id="ai-review-items">${r.items.map(i=>`<section class="editor-item ai-item" data-search-names="${searchNames([i.name])}"><label>Exercício<input class="ai-ex-name" value="${esc(i.name)}" maxlength="100" required></label><label>Grupo muscular<select class="ai-muscle">${muscles.map(m=>`<option ${i.muscle===m?'selected':''}>${m}</option>`).join('')}</select></label>
    <p class="ai-duplicate muted"></p><div class="fields"><label>Séries<input class="ai-sets" type="number" min="1" max="6" value="${i.sets}" required></label><label>Repetições<input class="ai-reps" type="number" min="1" max="30" value="${i.reps}" required></label><label>Descanso (s)<input class="ai-rest" type="number" min="0" max="300" value="${i.rest}" required></label></div>
    <div class="actions"><button type="button" class="secondary ai-ex-only">Revisar e salvar só este exercício</button><button type="button" class="danger ai-remove">Remover</button></div></section>`).join('')}</div>
    <label class="check-label"><input id="ai-reviewed" type="checkbox" required> Revisei os exercícios e confirmo salvar esta rotina e os novos exercícios no catálogo.</label><button>Confirmar e salvar rotina</button><p id="ai-review-error" class="muted" role="status"></p></form>`);
  document.querySelectorAll('.ai-item').forEach(row=>{
    const duplicate=()=>{row.dataset.searchNames=JSON.stringify([row.querySelector('.ai-ex-name').value]);const match=exercises.find(e=>normalizeSearch(e.name)===normalizeSearch(row.querySelector('.ai-ex-name').value));row.querySelector('.ai-duplicate').textContent=match?'Já existe: '+match.name+'. Será reutilizado.':'Novo exercício: será criado somente após confirmação.';row.querySelector('.ai-ex-only').disabled=!!match;};
    row.querySelector('.ai-ex-name').oninput=duplicate;duplicate();row.querySelector('.ai-remove').onclick=()=>row.remove();
    row.querySelector('.ai-ex-only').onclick=()=>exerciseEditor({name:row.querySelector('.ai-ex-name').value,muscle:row.querySelector('.ai-muscle').value});
  });
  $('#ai-review-form').onsubmit=async e=>{
    e.preventDefault();const form=e.target,button=form.querySelector('button:not([type])');
    const routine={name:$('#ai-name').value,items:[...document.querySelectorAll('.ai-item')].map(row=>({name:row.querySelector('.ai-ex-name').value,muscle:row.querySelector('.ai-muscle').value,sets:+row.querySelector('.ai-sets').value,reps:+row.querySelector('.ai-reps').value,rest:+row.querySelector('.ai-rest').value}))};
    if(!await confirmAction('Salvar a rotina revisada e adicionar os novos exercícios ao catálogo?'))return;
    button.disabled=true;
    try{await api('ai/import','POST',{routine,goal:$('#ai-review-goal').value,reviewed:$('#ai-reviewed').checked});dialog.close();await load();await render();notify('Rotina revisada e exercícios salvos.','success');}
    catch(error){$('#ai-review-error').textContent=error.message;}finally{if(button.isConnected)button.disabled=false;}
  };
}

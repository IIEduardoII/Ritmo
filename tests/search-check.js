// Executa o filtro real com linhas em memória, sem rede e sem Gemini.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8');
const helpers=source.split('\n').filter(line=>line.startsWith('const normalizeSearch=')||line.startsWith('function filterExercises(')||line.startsWith('const nameMatches=')||line.startsWith('function pickerResults(')||line.startsWith('function bindNameSearch(')).join('\n');
const original=['Supino Reto','Elevação lateral','Agachamento'];
const rows=original.map(name=>({dataset:{exName:name},textContent:name,hidden:false}));
const context=vm.createContext({document:{querySelectorAll:()=>rows},fetch:()=>{throw Error('A pesquisa não deve fazer requisições');}});
vm.runInContext(helpers,context);
for(const query of ['Supino Reto','SUPINO RÊTO','supinoreto','  sÚpInO\tRÊTO  ','supino']){
 context.query=query;vm.runInContext('filterExercises(query)',context);
 assert.deepEqual(rows.map(row=>row.hidden),[false,true,true],query);
}
context.query='elevacaoLATERAL';vm.runInContext('filterExercises(query)',context);
assert.deepEqual(rows.map(row=>row.hidden),[true,false,true]);
context.query='Catálogo';vm.runInContext('filterExercises(query)',context);
assert.ok(rows.every(row=>row.hidden)); // Somente nome, sem grupo/rótulo/ações.
context.query='';vm.runInContext('filterExercises(query)',context);
assert.ok(rows.every(row=>!row.hidden));
assert.deepEqual(rows.map(row=>row.textContent),original);
assert.ok(source.includes('data-ex-name="${esc(e.name)}"'));
assert.ok(source.includes("$('#search-ex').oninput=e=>filterExercises(e.target.value)"));
context.exercises=[{id:1,name:'Supino Reto'},{id:2,name:'Elevação lateral'}];
vm.runInContext("let result=pickerResults('SUPINORÊTO',2); if(result.matches.length!==1||result.matches[0].id!==1||!result.options.some(e=>e.id===2))throw Error('Seleção atual perdida');",context);
vm.runInContext("if(!nameMatches('Treino Á','treinoa')||!nameMatches('Supino reto','SUPINORÊTO'))throw Error('Busca compartilhada inválida');",context);
const count={textContent:''};
const input={value:'SUPINORÊTO',dataset:{searchTarget:'[data-routine-card]'},closest:()=>({querySelector:()=>count})};
const cards=[{dataset:{searchNames:JSON.stringify(['Treino A','Supino Reto'])},hidden:false},{dataset:{searchNames:JSON.stringify(['Treino B','Agachamento'])},hidden:false}];
context.root={querySelectorAll:selector=>selector==='[data-search-target]'?[input]:cards};
vm.runInContext('bindNameSearch(root)',context);input.oninput();
assert.deepEqual(cards.map(row=>row.hidden),[false,true]);
assert.equal(count.textContent,'1 de 2 resultado(s)');
input.value='nada';input.oninput();assert.ok(cards.every(row=>row.hidden));
assert.equal(count.textContent,'Nenhum nome encontrado.');
input.value='';input.oninput();assert.ok(cards.every(row=>!row.hidden));
console.log('OK: busca por nome, acentos/maiúsculas/espaços, trechos, vazio, grafia original e filtro sem rede.');

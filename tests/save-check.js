// No packages: deferred network verifies save coalescing, acknowledgement and retry.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../frontend/app.js'),'utf8');
const start=source.indexOf('let pendingSave='),end=source.indexOf('async function historyView',start);
let snapshot={notes:'a',items:[]},calls=[],deferred=[],fail=false;
const state={textContent:'',dataset:{}},button={disabled:false,isConnected:true};
const context={active:{id:7},saving:Promise.resolve(),performance,console:{debug(){}},Promise,JSON,
 $:selector=>selector==='#save-state'?state:button,collectWorkout:()=>structuredClone(snapshot),
 api:(_path,_method,payload)=>{calls.push(payload);return new Promise((resolve,reject)=>deferred.push(()=>fail?reject(Error('offline')):resolve({id:7,...payload})))}};
vm.createContext(context);vm.runInContext(source.slice(start,end),context);
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 const p=context.queueSave();context.queueSave();await tick();assert.equal(calls.length,1);assert.equal(button.disabled,true);assert.equal(state.textContent,'Salvando…');
 snapshot.notes='b';context.queueSave();snapshot.notes='c';context.queueSave();
 deferred.shift()();await tick();assert.equal(calls.length,2);assert.equal(calls[1].notes,'c');
 assert.equal(state.textContent,'Salvando…');deferred.shift()();await p;
 assert.equal(button.disabled,false);assert.match(state.textContent,/salvas no servidor/);
 await context.queueSave();assert.equal(calls.length,2); // unchanged payload never resubmitted
 snapshot.notes='unsaved';fail=true;const rejected=context.queueSave();await tick();deferred.shift()();await assert.rejects(rejected,/offline/);
 assert.match(state.textContent,/Falha ao salvar/);assert.equal(snapshot.notes,'unsaved');assert.equal(button.disabled,false);
 fail=false;const retry=context.queueSave();await tick();deferred.shift()();await retry;
 const finish=context.queueSave(true);await tick();assert.equal(calls.at(-1).finish,true);deferred.shift()();await finish;
 console.log('OK: duplicate sends coalesced, latest edits retained, server acknowledgement, failure fields retained, retry and finish.');
})().catch(e=>{console.error(e);process.exitCode=1});

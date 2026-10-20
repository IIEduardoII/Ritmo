const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8');
let entries=[],notifications=[],offline=false,apiCalls=0;
const context={authenticated:true,Date,Intl,Set,window:{focus(){}},location:{hash:''},
 api:async()=>{apiCalls++;if(offline)throw Error('offline');return entries},
 Notification:class {static permission='granted';constructor(title,options){notifications.push(options)}}};
vm.createContext(context);
vm.runInContext("let reminderEnabled=true,reminderSchedules=[],reminderSent=new Set(),remindersChecking=false;"+source.slice(source.indexOf('async function checkReminders(){'),source.indexOf('setInterval(checkReminders,30000)')),context);
const due={id:1,status:'agendado',scheduled_at:new Date().toISOString(),routine_name:'Teste'};
(async()=>{
 entries=[due];offline=true;await context.checkReminders();assert.equal(notifications.length,0);
 offline=false;await context.checkReminders();assert.equal(notifications.length,1);await context.checkReminders();assert.equal(notifications.length,1);
 entries=[{...due,id:2,status:'concluído'},{...due,id:3,scheduled_at:new Date(Date.now()-120000).toISOString()}];await context.checkReminders();assert.equal(notifications.length,1);
 vm.runInContext('reminderEnabled=false',context);const previous=apiCalls;await context.checkReminders();assert.equal(apiCalls,previous);
 vm.runInContext('reminderEnabled=true',context);context.Notification.permission='denied';await context.checkReminders();assert.equal(apiCalls,previous);
 console.log('OK: servidor indisponível não notifica; agendado notifica uma vez; concluído/atrasado não; desativação e permissão respeitadas.');
})().catch(e=>{console.error(e);process.exitCode=1});

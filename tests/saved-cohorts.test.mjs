import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {once} from 'node:events';
import {fork} from 'node:child_process';
import {mkdtemp, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {bridgePayload} from '../identity/cohorts.mjs';

const cases = [
  {synthetic:true, case_id:'SYNTH-CASE-0001', gender:'female', age:50, auth_resource_path:'/synthetic'},
  {synthetic:true, case_id:'SYNTH-CASE-0002', gender:'male', age:70, auth_resource_path:'/synthetic'},
  {synthetic:true, case_id:'SYNTH-CASE-0003', gender:'female', age:80, auth_resource_path:'/synthetic'},
];
const saved = (filter0, extra={}) => ({type:'tvs', tvs:{term:{type:'cohort', id:'saved-id', name:'Saved selection', filter0}, ...extra}});
const ids = item => item.tvs.term.values.synthetic.list.map(v=>v.sample);

test('saved cohorts preserve Boolean structure, negation, and native filters', () => {
  const female = saved({in:{gender:['female']}});
  const male = saved({in:{case_id:['SYNTH-CASE-0002']}}, {isnot:true});
  const native = {type:'tvs', tvs:{term:{type:'categorical', id:'gender'}, values:[{key:'female'}]}};
  const filter = {type:'tvslst', in:false, join:'or', lst:[female, {type:'tvslst', in:true, join:'and', lst:[male, native]}]};
  const original = structuredClone(filter);
  const result = bridgePayload({filter}, cases).filter;
  assert.equal(result.in, false);
  assert.equal(result.join, 'or');
  assert.deepEqual(ids(result.lst[0]), [1,3]);
  assert.deepEqual(ids(result.lst[1].lst[0]), [2]);
  assert.equal(result.lst[1].lst[0].tvs.isnot, true);
  assert.deepEqual(result.lst[1].lst[1], native);
  assert.deepEqual(filter, original, 'the saved cohort definition is not mutated');
});

test('DE groups resolve their own saved cohorts and intersect any active cohort', () => {
  const result = bridgePayload({filter0:{in:{gender:['female']}}, samplelst:{groups:[
    {name:'First group', filter:{type:'tvslst', in:true, join:'', lst:[saved({'>=':{age:60}})]}},
    {name:'Second group', filter0:{in:{gender:['male']}}, filter:saved({in:{case_id:['SYNTH-CASE-0002']}})},
  ]}}, cases);
  assert.deepEqual(ids(result.filter.lst[0]), [1,3]);
  assert.deepEqual(ids(result.samplelst.groups[0].filter.lst[0]), [2,3]);
  assert.deepEqual(result.samplelst.groups[1].filter.lst.map(ids), [[2],[2]]);
  assert.equal(result.samplelst.groups[0].name, 'First group');
});

test('empty selections stay empty and incomplete saved cohorts fail explicitly', () => {
  assert.deepEqual(ids(bridgePayload({filter:saved({in:{case_id:['SYNTH-CASE-absent']}})},cases).filter), []);
  assert.deepEqual(ids(bridgePayload({filter:saved('{}')},cases).filter), [1,2,3]);
  for (const term of [{type:'cohort'}, {type:'cohort',filter0:null}]) {
    assert.throws(()=>bridgePayload({filter:{type:'tvs',tvs:{term}}},cases),/missing its case filter/);
  }
  assert.throws(()=>bridgePayload({filter:saved({in:{unknown:['x']}})},cases),/Unsupported/);
});

test('gateway bridges saved-cohort GETs and DE POST groups without filter0', async t => {
  const received=[];
  const upstream=http.createServer(async(req,res)=>{
    const chunks=[];for await(const chunk of req)chunks.push(chunk);
    received.push({url:req.url,method:req.method,body:JSON.parse(Buffer.concat(chunks).toString()||'{}')});
    res.end('{}');
  });
  upstream.listen(0,'127.0.0.1');await once(upstream,'listening');
  t.after(()=>{upstream.closeAllConnections();upstream.close();});
  const dir=await mkdtemp(join(tmpdir(),'mmrf-saved-cohorts-'));
  t.after(()=>rm(dir,{recursive:true,force:true}));
  await writeFile(join(dir,'cases.json'),JSON.stringify(cases));
  await writeFile(join(dir,'files.json'),'[]');
  const reservation=http.createServer();reservation.listen(0,'127.0.0.1');await once(reservation,'listening');
  const port=reservation.address().port;await new Promise(resolve=>reservation.close(resolve));
  const child=fork(fileURLToPath(new URL('../identity/server.mjs',import.meta.url)),[],{env:{...process.env,PORT:String(port),BIND_ADDRESS:'127.0.0.1',SYNTHETIC_SANDBOX:'1',DATA_DIR:dir,PROTEINPAINT_ORIGIN:`http://127.0.0.1:${upstream.address().port}`},stdio:'ignore'});
  t.after(()=>child.kill());
  const origin=`http://127.0.0.1:${port}`;
  let ready=false;
  for(let i=0;i<100;i++){
    try{ready=(await fetch(origin+'/sandbox/status')).ok;}catch{}
    if(ready)break;
    await new Promise(resolve=>setTimeout(resolve,20));
  }
  assert.equal(ready,true);
  const filter={type:'tvslst',in:true,join:'',lst:[saved({in:{gender:['female']}})]};
  const params=new URLSearchParams({genome:'hg38',dslabel:'MMRF',getsamplecount:'1',filter:JSON.stringify(filter)});
  assert.equal((await fetch(origin+'/protein-paint/termdb?'+params)).status,200);
  assert.equal(received.at(-1).method,'POST');
  assert.equal(received.at(-1).url,'/termdb');
  assert.deepEqual(ids(received.at(-1).body.filter.lst[0]),[1,3]);
  const payload={genome:'hg38',dslabel:'MMRF',samplelst:{groups:[{name:'Saved',filter} ]},preAnalysis:true};
  assert.equal((await fetch(origin+'/protein-paint/termdb/DE',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)})).status,200);
  assert.deepEqual(ids(received.at(-1).body.samplelst.groups[0].filter.lst[0]),[1,3]);
  assert.equal(received.at(-1).body.preAnalysis,true);
});

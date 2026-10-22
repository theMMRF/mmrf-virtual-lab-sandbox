import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {once} from 'node:events';
import {createAccessServer, publicOrigin} from '../identity/access.mjs';
import {fork} from 'node:child_process';
import {mkdtemp, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

test('hosted entry refuses anonymous access and strips team credentials before proxying', async t => {
  let received;
  const upstream = http.createServer(async (req,res)=>{
    const chunks=[]; for await (const part of req) chunks.push(part);
    received={url:req.url, headers:req.headers, body:Buffer.concat(chunks).toString()};
    res.end('synthetic response');
  });
  upstream.listen(0,'127.0.0.1'); await once(upstream,'listening');
  t.after(()=>upstream.close());
  const password='synthetic-unit-test-password-'.repeat(2);
  const server=createAccessServer({username:'sandbox',password,origin:'https://syntheticfixture.cloudfront.net',
    upstream:`http://127.0.0.1:${upstream.address().port}`});
  server.listen(0,'127.0.0.1'); await once(server,'listening');
  t.after(()=>server.close());
  const origin=`http://127.0.0.1:${server.address().port}`;
  for (const path of ['/','/sandbox/session','/guppy/graphql','/protein-paint/termdb','/user/user']) {
    const response=await fetch(origin+path);
    assert.equal(response.status,401);
    assert.match(response.headers.get('www-authenticate'),/^Basic /);
  }
  assert.equal(received,undefined);
  assert.deepEqual(await (await fetch(origin+'/_status')).json(),{status:'OK'});
  const response=await fetch(origin+'/guppy/graphql?x=1',{method:'POST',body:'{"synthetic":true}',headers:{
    authorization:'Basic '+Buffer.from('sandbox:'+password).toString('base64'),
    'x-forwarded-proto':'http','x-forwarded-host':'untrusted.invalid',forwarded:'host=untrusted.invalid',
  }});
  assert.equal(await response.text(),'synthetic response');
  assert.equal(received.url,'/guppy/graphql?x=1');
  assert.equal(received.body,'{"synthetic":true}');
  assert.equal(received.headers.authorization,undefined);
  assert.equal(received.headers.forwarded,undefined);
  assert.equal(received.headers['x-forwarded-proto'],'https');
  assert.equal(received.headers.host,'syntheticfixture.cloudfront.net');
  assert.equal(response.headers.get('cache-control'),'no-store');
});

test('hosted configuration fails closed for missing passwords or invalid origins',()=>{
  for (const origin of ['http://syntheticfixture.cloudfront.net','https://virtuallab.themmrf.org','https://x.cloudfront.net/else','https://x.cloudfront.net.evil.invalid']) {
    assert.throws(()=>publicOrigin(origin));
  }
  assert.throws(()=>createAccessServer({username:'sandbox',password:'short',origin:'https://x.cloudfront.net'}));
});

test('upstream failures return 502 before headers and abort partial streamed responses',async t=>{
  const upstream=http.createServer((req,res)=>{
    if(req.url==='/before') return res.destroy();
    res.writeHead(200,{'content-type':'application/json'});
    res.write('{"incomplete":');
    setTimeout(()=>res.destroy(),30);
  });
  upstream.listen(0,'127.0.0.1'); await once(upstream,'listening');
  t.after(()=>upstream.close());
  const password='synthetic-unit-test-password-'.repeat(2);
  const server=createAccessServer({username:'sandbox',password,origin:'https://syntheticfixture.cloudfront.net',
    upstream:`http://127.0.0.1:${upstream.address().port}`});
  server.listen(0,'127.0.0.1'); await once(server,'listening'); t.after(()=>server.close());
  const origin=`http://127.0.0.1:${server.address().port}`;
  const options={headers:{authorization:'Basic '+Buffer.from('sandbox:'+password).toString('base64')}};
  const unavailable=await fetch(origin+'/before',options);
  assert.equal(unavailable.status,502);
  assert.equal(unavailable.headers.get('cache-control'),'no-store');
  assert.equal(await unavailable.text(),'Synthetic service unavailable');
  await assert.rejects(async()=>{const response=await fetch(origin+'/after',options);await response.text();});
});

test('hosted identity emits HTTPS download URLs from its configured origin', async t=>{
  const directory=await mkdtemp(join(tmpdir(),'mmrf-identity-origin-'));
  t.after(()=>rm(directory,{recursive:true,force:true}));
  await writeFile(join(directory,'cases.json'),JSON.stringify([{synthetic:true,case_id:'SYNTH-CASE-0001',
    project_id:'SYNTHETIC-MM',auth_resource_path:'/programs/SYNTHETIC/projects/MM'}]));
  await writeFile(join(directory,'files.json'),JSON.stringify([{file_id:'SYNTH-FILE-0001',
    file_name:'SYNTH-SAMPLE-0001.synthetic.fasta',file_size:1,md5sum:'synthetic',acl:['SYNTHETIC-MM']}]));
  const reservation=http.createServer(); reservation.listen(0,'127.0.0.1'); await once(reservation,'listening');
  const port=reservation.address().port; await new Promise(resolve=>reservation.close(resolve));
  const child=fork(fileURLToPath(new URL('../identity/server.mjs',import.meta.url)),[],{env:{...process.env,
    PORT:String(port),BIND_ADDRESS:'127.0.0.1',SYNTHETIC_SANDBOX:'1',DATA_DIR:directory,
    SANDBOX_PUBLIC_ORIGIN:'https://syntheticfixture.cloudfront.net'},stdio:'ignore'});
  t.after(()=>{child.kill();});
  let ready=false;
  for(let i=0;i<100;i++) {
    try {ready=(await fetch(`http://127.0.0.1:${port}/sandbox/status`)).ok;} catch {}
    if(ready) break;
    await new Promise(resolve=>setTimeout(resolve,20));
  }
  assert.equal(ready,true);
  const response=await fetch(`http://127.0.0.1:${port}/user/data/download/SYNTH-FILE-0001`);
  assert.equal((await response.json()).url,'https://syntheticfixture.cloudfront.net/sandbox/files/SYNTH-FILE-0001');
});

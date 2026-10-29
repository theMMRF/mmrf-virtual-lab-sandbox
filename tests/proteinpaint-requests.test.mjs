import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {once} from 'node:events';
import {fork} from 'node:child_process';
import {mkdtemp, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

test('ProteinPaint duplicate JSON POSTs retain cohort bridging and other media types remain unchanged', async t => {
  const received = [];
  const upstream = http.createServer(async (req, res) => {
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    received.push({url:req.url, method:req.method, headers:req.headers, body:Buffer.concat(chunks).toString()});
    res.end('{}');
  });
  upstream.listen(0, '127.0.0.1'); await once(upstream, 'listening');
  t.after(() => {upstream.closeAllConnections(); upstream.close();});
  const directory = await mkdtemp(join(tmpdir(), 'mmrf-pp-requests-'));
  t.after(() => rm(directory, {recursive:true, force:true}));
  const cases = Array.from({length:318}, (_, i) => ({synthetic:true, case_id:`SYNTH-CASE-${i}`,
    sample_id:`SYNTH-SAMPLE-${i}`, project_id:'SYNTHETIC-MM', auth_resource_path:'/synthetic'}));
  await writeFile(join(directory, 'cases.json'), JSON.stringify(cases));
  await writeFile(join(directory, 'files.json'), '[]');
  const reservation = http.createServer(); reservation.listen(0, '127.0.0.1'); await once(reservation, 'listening');
  const port = reservation.address().port; await new Promise(resolve => reservation.close(resolve));
  const target = `http://127.0.0.1:${upstream.address().port}`;
  const child = fork(fileURLToPath(new URL('../identity/server.mjs', import.meta.url)), [], {env:{...process.env,
    PORT:String(port), BIND_ADDRESS:'127.0.0.1', SYNTHETIC_SANDBOX:'1', DATA_DIR:directory,
    PROTEINPAINT_ORIGIN:target, FRONTEND_ORIGIN:target}, stdio:'ignore'});
  t.after(() => child.kill());
  const origin = `http://127.0.0.1:${port}`;
  let ready = false;
  for (let i=0; i<100; i++) {
    try {ready = (await fetch(origin+'/sandbox/status')).ok;} catch {}
    if (ready) break;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  assert.equal(ready, true);
  const duplicate = {'Content-Type':'application/json', 'content-type':'application/json'};
  const filter0 = {and:[{in:{case_id:cases.filter((_, i) => i%2 === 0).map(c => c.case_id)}}]};
  const native = {type:'tvs', tvs:{term:{id:'gender', type:'categorical'}, values:[{key:'female'}]}};
  const payload = {genome:'hg38', dslabel:'MMRF', filter0, filter:native};
  for (const path of ['/protein-paint/termdb/mds3?variant2samples=1', '/protein-paint/mds3']) {
    const response = await fetch(origin+path, {method:'POST', headers:duplicate, body:JSON.stringify(payload)});
    assert.equal(response.status, 200);
    const actual = received.at(-1);
    assert.equal(actual.url, path.slice('/protein-paint'.length));
    assert.equal(actual.method, 'POST');
    assert.equal(actual.headers['content-type'], 'application/json');
    const bridged = JSON.parse(actual.body);
    assert.equal(bridged.filter0, undefined);
    assert.deepEqual(bridged.filter.lst[0].tvs.term.values.synthetic.list,
      cases.flatMap((_, i) => i%2 === 0 ? [{sample:i+1}] : []));
    assert.deepEqual(bridged.filter.lst[1], native);
    assert.equal(Number(actual.headers['content-length']), Buffer.byteLength(actual.body));
  }
  for (const type of [
    'application/json; charset=utf-8, application/json; charset=utf-8',
    'Application/JSON; charset="UTF-8", application/json; charset=utf-8',
    'application/json, application/json; charset=utf-8',
  ]) {
    await fetch(origin+'/protein-paint/mds3', {method:'POST', headers:{'content-type':type}, body:JSON.stringify(payload)});
    const actual = received.at(-1);
    assert.equal(actual.headers['content-type'], 'application/json');
    assert.deepEqual(JSON.parse(actual.body).filter.lst[0].tvs.term.values.synthetic.list,
      cases.flatMap((_, i) => i%2 === 0 ? [{sample:i+1}] : []));
    assert.deepEqual(JSON.parse(actual.body).filter.lst[1], native);
  }
  // A large GET still becomes a POST, using the same case selection.
  await fetch(origin+'/protein-paint/mds3?'+new URLSearchParams({filter0:JSON.stringify(filter0), genome:'hg38'}));
  assert.equal(received.at(-1).method, 'POST');
  assert.deepEqual(JSON.parse(received.at(-1).body).filter.lst[0].tvs.term.values.synthetic.list,
    cases.flatMap((_, i) => i%2 === 0 ? [{sample:i+1}] : []));
  for (const type of ['text/plain', 'application/json, text/plain', 'application/json,',
    'application/json; charset=utf-16, application/json; charset=utf-16',
    'application/json; profile="other", application/json; profile="other"']) {
    await fetch(origin+'/protein-paint/mds3', {method:'POST', headers:{'content-type':type}, body:'{}'});
    assert.equal(received.at(-1).headers['content-type'], type);
  }
  await fetch(origin+'/unrelated', {method:'POST', headers:duplicate, body:'{}'});
  assert.equal(received.at(-1).headers['content-type'], 'application/json, application/json');
});

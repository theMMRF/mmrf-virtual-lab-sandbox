import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createIdentity } from './token.mjs';
import { bridgePayload } from './cohorts.mjs';

if (process.env.SYNTHETIC_SANDBOX !== '1') throw new Error('This service requires SYNTHETIC_SANDBOX=1');
const identity = createIdentity();
const dataDir = resolve(process.env.DATA_DIR || fileURLToPath(new URL('../generated/', import.meta.url)));
const cases = JSON.parse(await readFile(join(dataDir, 'cases.json')));
const files = JSON.parse(await readFile(join(dataDir, 'files.json')));
if (!cases.length || cases.some(c => !c.synthetic || !c.case_id.startsWith('SYNTH-CASE-'))) throw new Error('Only generated synthetic cases are allowed');
const resources = ['/mmrf_metadata', '/programs/SYNTHETIC/projects/MM'];
const terms = { id: 1, version: 'synthetic-v1', effective_at: '2026-01-01T00:00:00Z', terms_url: null,
  terms_content: 'Synthetic demonstration data only. No patient data or clinical interpretation.', content_format: 'plain_text' };
const targets = {
  frontend: process.env.FRONTEND_ORIGIN || 'http://frontend:3000',
  guppy: process.env.GUPPY_ORIGIN || 'http://guppy:8080',
  analysis: process.env.ANALYSIS_ORIGIN || 'http://analysis:8000',
  proteinpaint: process.env.PROTEINPAINT_ORIGIN || 'http://proteinpaint:3000',
};
// This launcher can only route to its own service names or loopback. It cannot
// point its disposable identity at a real commons through environment settings.
for (const [name, value] of Object.entries(targets)) {
  const url = new URL(value);
  if (url.protocol !== 'http:' || ![name, 'localhost', '127.0.0.1'].includes(url.hostname) ||
      url.username || url.password || url.pathname !== '/' || url.search || url.hash) throw new Error(`Invalid sandbox ${name} origin`);
}
function json(res, value, status = 200) {
  res.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store' });
  res.end(JSON.stringify(value));
}
async function body(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 8 * 1024 * 1024) throw new Error('Request body too large');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}
const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://sandbox.invalid');
    const path = url.pathname;
    if (path === '/_status' || path === '/sandbox/status') return json(res, { status: 'OK', synthetic: true, cases: cases.length, csrf: 'synthetic-only' });
    if (path === '/sandbox/session') return json(res, { access_token: identity.issue(), expires_in: 1800, synthetic: true });
    if (path.startsWith('/sandbox/files/')) {
      const file = files.find(f => path === `/sandbox/files/${f.file_id}`);
      if (!file || !/^SYNTH-SAMPLE-[0-9]+\.synthetic\.fasta$/.test(file.file_name)) return json(res, {error: 'Unknown synthetic file'}, 404);
      const content = await readFile(join(dataDir, file.file_name));
      res.writeHead(200, {'content-type': 'text/plain', 'content-disposition': `attachment; filename="${file.file_name}"`});
      return res.end(content);
    }
    if (path.startsWith('/index/index/')) {
      const file = files.find(f => path === `/index/index/${f.file_id}`);
      if (!file) return json(res, {error: 'Unknown synthetic file'}, 404);
      return json(res, {did: file.file_id, file_name: file.file_name, size: file.file_size, hashes: {md5: file.md5sum},
        urls: [`http://${req.headers.host}/sandbox/files/${file.file_id}`], acl: ['SYNTHETIC-MM']});
    }
    if (path.startsWith('/user/data/download/')) {
      const file = files.find(f => path === `/user/data/download/${f.file_id}`);
      return file ? json(res, {url: `http://${req.headers.host}/sandbox/files/${file.file_id}`}) : json(res, {error: 'Unknown synthetic file'}, 404);
    }
    if (['/user/jwt/keys', '/jwt/keys'].includes(path)) return json(res, { keys: [['synthetic', identity.pem]] });
    if (path === '/.well-known/jwks.json') return json(res, { keys: [identity.jwk] });
    if (path === '/auth/request') {
      const input = JSON.parse((await body(req)).toString() || '{}');
      const token = req.headers.authorization?.replace(/^Bearer /i, '') || input.user?.token;
      const allowed = identity.valid(token) && input.requests?.length && input.requests.every(r => resources.includes(r.resource) && ['guppy', 'gen3-analysis'].includes(r.action?.service) && r.action?.method === 'read');
      return json(res, { auth: Boolean(allowed) }, allowed ? 200 : 403);
    }
    if (path === '/auth/resources' || path === '/auth/mapping') {
      const token = req.headers.authorization?.replace(/^Bearer /i, '');
      if (!identity.valid(token)) return json(res, { error: 'Synthetic token required' }, 401);
      return json(res, path.endsWith('/mapping') ? Object.fromEntries(resources.map(r => [r, [{ service: '*', method: 'read' }]])) : resources);
    }
    if (path.startsWith('/user/')) {
      if (path === '/user/user') return json(res, { user_id: 1, username: 'synthetic@example.invalid', name: 'Synthetic Developer',
        email: 'synthetic@example.invalid', is_admin: false, project_access: { 'SYNTHETIC-MM': ['read', 'read-storage'] },
        authz: Object.fromEntries(resources.map(r => [r, [{ service: '*', method: 'read' }]])) });
      if (path === '/user/csrf') return json(res, { csrf: 'synthetic-only' });
      if (path === '/user/credentials/cdis/access_token') return json(res, { error: 'Real credentials are not supported' }, 404);
      return json(res, {}, 404);
    }
    if (path.startsWith('/analysis/v0/terms/')) {
      if (path.endsWith('/current')) return json(res, terms);
      if (path.endsWith('/status')) return json(res, { has_accepted_latest_terms: true, current_terms: terms });
      return json(res, { accepted: true, has_accepted_latest_terms: true, terms_version_id: 1 });
    }
    let target = targets.frontend;
    let targetPath = req.url;
    if (path.startsWith('/guppy/')) { target = targets.guppy; targetPath = req.url.slice('/guppy'.length); }
    if (path.startsWith('/analysis/')) target = targets.analysis;
    let ppBody;
    if (path.startsWith('/protein-paint/')) {
      target = targets.proteinpaint;
      const ppUrl = new URL(req.url.slice('/protein-paint'.length), target);
      if (ppUrl.searchParams.has('filter0')) {
        const payload = Object.fromEntries(ppUrl.searchParams);
        const bridged = bridgePayload(payload, cases);
        ppUrl.searchParams.delete('filter0');
        if (bridged.filter) ppUrl.searchParams.set('filter', JSON.stringify(bridged.filter));
      }
      targetPath = ppUrl.pathname + ppUrl.search;
      if (req.method === 'POST' && req.headers['content-type']?.includes('application/json')) {
        ppBody = Buffer.from(JSON.stringify(bridgePayload(JSON.parse((await body(req)).toString()), cases)));
      }
    }
    if (path.startsWith('/authz/')) {
      if (path.endsWith('/resources')) return json(res, resources);
      if (path.endsWith('/mapping')) return json(res, Object.fromEntries(resources.map(r => [r, [{ service: '*', method: 'read' }]])));
      return json(res, {}, 404);
    }
    if (path.startsWith('/lw-workspace/')) return json(res, { status: 'Stopped' });
    const token = identity.issue();
    const headers = { ...req.headers, host: new URL(target).host, authorization: `Bearer ${token}`,
      cookie: `access_token=${token}`, 'x-forwarded-host': req.headers.host, 'x-forwarded-proto': 'http' };
    delete headers['proxy-authorization'];
    if (ppBody) {
      headers['content-length'] = String(ppBody.length);
      delete headers['transfer-encoding'];
    }
    const destination = new URL(targetPath, target);
    if (destination.origin !== new URL(target).origin) return json(res, { error: 'Invalid sandbox path' }, 400);
    const upstream = http.request(destination, { method: req.method, headers }, response => {
      res.writeHead(response.statusCode || 502, { ...response.headers, 'set-cookie': `access_token=${token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=1800` });
      response.pipe(res);
    });
    upstream.setTimeout(180000, () => upstream.destroy());
    upstream.on('error', () => { if (!res.headersSent) json(res, { error: 'Sandbox service unavailable' }, 502); else res.destroy(); });
    req.on('aborted', () => upstream.destroy());
    res.on('close', () => { if (!res.writableEnded) upstream.destroy(); });
    if (ppBody) upstream.end(ppBody);
    else req.pipe(upstream);
  } catch (err) {
    console.error(err.message);
    if (!res.headersSent) json(res, { error: 'Invalid sandbox request' }, 400);
    else res.destroy();
  }
});
server.listen(Number(process.env.PORT || 8080), process.env.BIND_ADDRESS || '0.0.0.0');

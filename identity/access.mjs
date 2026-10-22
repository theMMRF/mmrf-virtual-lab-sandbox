// A separate entry point protects hosted demos without changing the internal
// synthetic identity contract used by the frontend, Guppy and analysis service.
import http from 'node:http';
import {createHash, timingSafeEqual} from 'node:crypto';
import {pathToFileURL} from 'node:url';

const digest = value => createHash('sha256').update(value).digest();
export function publicOrigin(value) {
  const origin = new URL(value);
  if (origin.protocol !== 'https:' || !/^[a-z0-9]+\.cloudfront\.net$/.test(origin.hostname) ||
      origin.port || origin.username || origin.password || origin.pathname !== '/' || origin.search || origin.hash) {
    throw new Error('A canonical CloudFront HTTPS origin is required');
  }
  return origin.origin;
}

export function createAccessServer({username, password, origin, upstream = 'http://identity:8080'}) {
  origin = publicOrigin(origin);
  const target = new URL(upstream);
  if (!username || username.includes(':') || !password || password.length < 24 ||
      target.protocol !== 'http:' || !['identity', 'localhost', '127.0.0.1'].includes(target.hostname) ||
      target.username || target.password || target.pathname !== '/' || target.search || target.hash) {
    throw new Error('Access gateway requires a generated password and local upstream');
  }
  const expected = digest(`Basic ${Buffer.from(`${username}:${password}`).toString('base64')}`);
  return http.createServer({maxHeaderSize: 65536}, (req, res) => {
    if (req.url === '/_status' && req.method === 'GET') {
      res.writeHead(200, {'content-type': 'application/json', 'cache-control': 'no-store'});
      return res.end('{"status":"OK"}');
    }
    if (!timingSafeEqual(digest(req.headers.authorization || ''), expected)) {
      res.writeHead(401, {'www-authenticate': 'Basic realm="Synthetic Virtual Lab", charset="UTF-8"',
        'cache-control': 'no-store', 'content-type': 'text/plain'});
      return res.end('Team access credentials required.');
    }
    const destination = new URL(req.url, target);
    if (!req.url.startsWith('/') || destination.origin !== target.origin) {
      res.writeHead(400); return res.end();
    }
    const canonical = new URL(origin);
    const headers = {...req.headers, host: canonical.host,
      'x-forwarded-host': canonical.host, 'x-forwarded-proto': 'https'};
    delete headers.authorization;
    delete headers['proxy-authorization'];
    delete headers.forwarded;
    const proxyFailure = () => {
      if (res.destroyed || res.writableEnded) return;
      if (res.headersSent) return res.destroy();
      res.writeHead(502, {'cache-control': 'no-store', 'content-type': 'text/plain'});
      res.end('Synthetic service unavailable');
    };
    const proxy = http.request(destination, {method: req.method, headers}, response => {
      response.on('error', proxyFailure);
      response.on('aborted', proxyFailure);
      res.writeHead(response.statusCode || 502, {...response.headers, 'cache-control': 'no-store',
        'strict-transport-security': 'max-age=86400', 'x-content-type-options': 'nosniff'});
      response.pipe(res);
    });
    proxy.setTimeout(180000, () => proxy.destroy());
    proxy.on('error', proxyFailure);
    req.on('aborted', () => proxy.destroy());
    res.on('close', () => {if (!res.writableEnded) proxy.destroy();});
    req.pipe(proxy);
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  createAccessServer({username: process.env.SANDBOX_ACCESS_USERNAME,
    password: process.env.SANDBOX_ACCESS_PASSWORD, origin: process.env.SANDBOX_PUBLIC_ORIGIN,
    upstream: process.env.SANDBOX_UPSTREAM_ORIGIN || 'http://identity:8080'})
    .listen(Number(process.env.PORT || 8080), '0.0.0.0');
}

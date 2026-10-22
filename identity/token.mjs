import { generateKeyPairSync, sign, verify } from 'node:crypto';

// Ephemeral per-process keys; no real identity provider, credentials, or key files.
export function createIdentity() {
  const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
  const encode = value => Buffer.from(JSON.stringify(value)).toString('base64url');
  function issue() {
    const now = Math.floor(Date.now() / 1000);
    const payload = { iss: 'mmrf-synthetic-sandbox', sub: '1', iat: now, exp: now + 1800,
      aud: ['openid', 'user', 'fence', 'guppy', 'gen3-analysis'],
      context: { user: { name: 'Synthetic Developer', username: 'synthetic@example.invalid', email: 'synthetic@example.invalid', admin: false } } };
    const value = `${encode({ alg: 'RS256', typ: 'JWT', kid: 'synthetic' })}.${encode(payload)}`;
    return `${value}.${sign('RSA-SHA256', Buffer.from(value), privateKey).toString('base64url')}`;
  }
  function valid(token) {
    try {
      const parts = token.split('.');
      if (parts.length !== 3) return false;
      const payload = JSON.parse(Buffer.from(parts[1], 'base64url'));
      return payload.iss === 'mmrf-synthetic-sandbox' && payload.exp > Date.now() / 1000 &&
        verify('RSA-SHA256', Buffer.from(parts.slice(0, 2).join('.')), publicKey, Buffer.from(parts[2], 'base64url'));
    } catch { return false; }
  }
  return { issue, valid, pem: publicKey.export({ type: 'spki', format: 'pem' }), jwk: { ...publicKey.export({ format: 'jwk' }), kid: 'synthetic', alg: 'RS256', use: 'sig' } };
}

// Only file formats and object shapes are used. Every fixture scalar is replaced;
// no historical example patient values are shipped in a sandbox image.
import { readdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
const root = process.argv[2];
if (!root) throw new Error('Supply the disposable frontend build directory');
const fixtureDirs = [
  'src/core/data', 'src/core/features/cases/data', 'src/core/features/projects/data',
  'src/core/genomic/__mocks__/data', 'src/features/cases/data', 'src/features/files/data',
  'src/features/cohortComparison/data', 'src/features/genomic/data',
];
let counter = 0;
function synthetic(value) {
  if (value === null) return null;
  if (Array.isArray(value)) return value.length ? [synthetic(value[0])] : [];
  if (typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [
    /^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(key) ? `SYNTHETIC-KEY-${++counter}` : key, synthetic(item),
  ]));
  if (typeof value === 'number') return 1;
  if (typeof value === 'boolean') return false;
  return `SYNTHETIC-${++counter}`;
}
async function sanitize(dir) {
  for (const file of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, file.name);
    if (file.isDirectory()) await sanitize(path);
    else if (file.name.endsWith('.json')) await writeFile(path, JSON.stringify(synthetic(JSON.parse(await readFile(path, 'utf8')))) + '\n');
  }
}
for (const dir of fixtureDirs) await sanitize(join(root, dir));
const sessionPath = join(root, 'config/gen3/session.json');
const session = JSON.parse(await readFile(sessionPath, 'utf8'));
session.sessionConfig.monitorWorkspace = false;
await writeFile(sessionPath, JSON.stringify(session, null, 2) + '\n');
console.log('Replaced historical frontend fixture values with synthetic placeholders');

// Narrow compatibility fix for the pinned public ProteinPaint server, not ppmmrf.
// Native prebuilt scatter plots otherwise ignore filters when no color/shape term
// is selected. Apply the existing native SQL filter before reading plot samples.
// Remove this patch when the public server includes equivalent filtering.
import {readFileSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
const root = process.argv[2];
if (!root) throw new Error('Supply the installed public ProteinPaint server directory');
if (JSON.parse(readFileSync(join(root, 'package.json'))).version !== '2.216.0') {
  throw new Error('Revalidate the scatter filter patch for a new ProteinPaint version');
}
const file = join(root, 'src/app.js');
const source = readFileSync(file, 'utf8');
const before = 'return [readSamples(plot.referenceSamples), readSamples(plot.filterableSamples)];';
if (source.split(before).length !== 2 || !source.includes('async function getSamples2(req2, ds, plot)')) {
  throw new Error('Public ProteinPaint scatter implementation changed; refusing an unverified patch');
}
const after = `const allowedIds = req2.query?.filter
    ? new Set((await get_samples(req2.query, ds)).map(row => row.id)) : null;
  return [readSamples(plot.referenceSamples), readSamples(plot.filterableSamples.filter(
    sample => !allowedIds || allowedIds.has(sample.sampleId)
  ))];`;
writeFileSync(file, source.replace(before, after));

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
// Fresh configuration against the public ProteinPaint Mds3 contract.
// No private ppmmrf adapter code or deployment configuration is copied here.
export default function (_common, refs) {
  const cases = JSON.parse(readFileSync(join(refs.serverconfig.tpmasterdir, 'cases.json')));
  const sampleToCase = new Map(cases.flatMap((record, index) => [[record.sample_id, record.case_id], [index + 1, record.case_id]]));
  const variants = JSON.parse(readFileSync(join(refs.serverconfig.tpmasterdir, 'variants.json')));
  function selected(record, index, filter) {
    if (!filter) return true;
    if (typeof filter === 'string') return selected(record, index, JSON.parse(filter));
    if (filter.type === 'tvslst') {
      const results = filter.lst.map(item => selected(record, index, item));
      const match = filter.join === 'or' ? results.some(Boolean) : results.every(Boolean);
      return filter.in === false ? !match : match;
    }
    const tvs = filter.tvs;
    if (!tvs?.term) throw new Error('Unsupported synthetic ProteinPaint filter');
    let match;
    if (tvs.term.type === 'samplelst') {
      match = Object.values(tvs.term.values).some(group => group.list.some(sample => (sample.sampleId || sample.sample) === index + 1));
    } else if (tvs.term.type === 'categorical') {
      match = tvs.values.some(v => v.key === record[tvs.term.id]);
    } else if (['integer', 'float'].includes(tvs.term.type)) {
      const value = record[tvs.term.id];
      match = tvs.ranges.some(r => (r.startunbounded || (r.startinclusive ? value >= r.start : value > r.start)) &&
        (r.stopunbounded || (r.stopinclusive ? value <= r.stop : value < r.stop)));
    } else throw new Error('Unsupported synthetic ProteinPaint filter type');
    return tvs.isnot ? !match : match;
  }
  return {
    isMds3: true,
    label: 'Synthetic MMRF',
    cohort: {
      db: { file: 'termdb.sqlite' },
      termdb: {
        allowedTermTypes: ['geneVariant'],
        displaySampleIds: () => true,
        timeUnit: 'years',
        matrix: { appName: 'OncoMatrix' },
        convertSampleId: { get: inputs => Object.fromEntries(inputs.map(sample => [sample, sampleToCase.get(sample)])) },
      },
      scatterplots: { plots: [{name: 'Bulk RNA-seq UMAP', description: 'Random synthetic coordinates; no biological structure', dimension: 2,
        file: 'bulk-umap.tsv', colorTW: {id: 'gender'}, shapeTW: {id: 'vital_status'}}] },
    },
    queries: {
      topMutatedGenes: {
        get: async query => {
          const allowed = new Set(cases.flatMap((record, index) => selected(record, index, query.filter) ? [record.sample_id] : []));
          const counts = new Map();
          for (const variant of variants) {
            if (!allowed.has(variant.sample_id)) continue;
            if (!counts.has(variant.symbol)) counts.set(variant.symbol, new Set());
            counts.get(variant.symbol).add(variant.sample_id);
          }
          return [...counts].sort((a, b) => b[1].size - a[1].size).slice(0, Math.min(query.maxGenes || 50, 50))
            .map(([gene, samples]) => ({ gene, mutationStat: [{ dt: 1, count: samples.size }] }));
        },
      },
      snvindel: { forTrack: true, byrange: { bcffile: 'variants.bcf.gz' } },
      cnv: {type: 'log2ratio', file: 'cnv.tsv.gz'},
      geneExpression: {file: 'expression.h5', unit: 'Synthetic TPM'},
      rnaseqGeneCount: {file: 'counts.h5'},
      topVariablyExpressedGenes: {},
      singleCell: {
        samples: {sampleColumns: [{termid: 'gender'}], extraSampleTabLabel: 'Synthetic sample'},
        data: {sameLegend: true, plots: [{name: 'UMAP', folder: 'singlecell/umap', fileSuffix: '_umap.txt',
          colorColumns: [{index: 3, name: 'Synthetic cell type'}], coordsColumns: {x: 1, y: 2}, selected: true}]},
        geneExpression: {folder: 'singlecell/expression'},
      },
    },
  };
}

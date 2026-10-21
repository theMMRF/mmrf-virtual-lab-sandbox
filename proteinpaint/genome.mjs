// Deliberately small, synthetic gene models. Coordinates are illustrative.
export default {
  species: 'human (synthetic fixtures)',
  genomefile: 'synthetic.fa',
  genedb: { dbfile: 'genes.sqlite' },
  tracks: [{__isgene: true, translatecoding: true, file: 'genes.bedj.gz', type: 'bedj', name: 'Synthetic gene models', stackheight: 16, stackspace: 1, vpad: 4, color: '#1D591D'}],
  defaultcoord: { chr: 'chr17', start: 29900, stop: 32200 },
  majorchr: 'chr1\t100000\nchr7\t100000\nchr12\t100000\nchr13\t100000\nchr17\t100000',
  minorchr: '',
};

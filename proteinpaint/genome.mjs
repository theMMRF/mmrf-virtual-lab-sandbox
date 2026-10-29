// Deliberately small, synthetic coordinate models with public reference protein sequences.
export default {
  species: 'human (synthetic fixtures)',
  genomefile: 'synthetic.fa',
  genedb: { dbfile: 'genes.sqlite' },
  tracks: [{__isgene: true, translatecoding: true, file: 'genes.bedj.gz', type: 'bedj', name: 'Synthetic gene models', stackheight: 16, stackspace: 1, vpad: 4, color: '#1D591D'}],
  defaultcoord: { chr: 'chr17', start: 29900, stop: 32200 },
  majorchr: 'chr1\t500000\nchr7\t500000\nchr8\t500000\nchr12\t500000\nchr13\t500000\nchr17\t500000',
  minorchr: '',
};

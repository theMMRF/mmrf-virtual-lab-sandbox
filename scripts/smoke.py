"""Exercise real sandbox APIs and cross-service synthetic ID consistency."""
import argparse
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--origin', default='http://127.0.0.1:3080')
args = parser.parse_args()
if not args.origin.startswith(('http://127.0.0.1:', 'http://localhost:')):
    raise SystemExit('Smoke tests only target a local sandbox or port-forward')
root = Path(__file__).resolve().parents[1]
cases = json.loads((root / 'generated/cases.json').read_text())
variants = json.loads((root / 'generated/variants.json').read_text())


def call(path, payload=None, raw=False):
    req = urllib.request.Request(args.origin + path, data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        raise AssertionError(f'{path}: HTTP {exc.code}: {exc.read().decode()[:1500]}') from exc
    if raw:
        return data
    value = json.loads(data)
    assert not value.get('error') and not value.get('errors'), (path, value)
    return value


for attempt in range(90):
    try:
        status = call('/sandbox/status')
        break
    except (OSError, AssertionError):
        if attempt == 89:
            raise
        time.sleep(2)
assert status['synthetic'] and status['cases'] == len(cases)
assert call('/api/auth/sessionToken')['status'] == 'issued'
print('PASS: credential-free frontend session')

female = [c for c in cases if c['gender'] == 'female']
cohort_filter = {'in': {'demographic.gender': ['female']}}
query = '''query($filter:JSON) {
  CaseCentric_case_centric(first:1000,filter:$filter) { case_id samples { sample_id } }
  CaseCentric__aggregation {case_centric(filter:$filter) {_totalCount}}
}'''
result = call('/guppy/graphql', {'query': query, 'variables': {'filter': cohort_filter}})['data']
assert result['CaseCentric__aggregation']['case_centric']['_totalCount'] == len(female)
assert {c['case_id'] for c in result['CaseCentric_case_centric']} == {c['case_id'] for c in female}
print(f'PASS: real Guppy cohort filtering ({len(cases)} -> {len(female)})')

query = '{ File_file(first:1000) { file_id cases { case_id } } }'
files = call('/guppy/graphql', {'query': query})['data']['File_file']
assert len(files) == len(cases)
assert all(f['file_id'].startswith('SYNTH-FILE-') and f['cases'][0]['case_id'].startswith('SYNTH-CASE-') for f in files)
sequence = call('/sandbox/files/SYNTH-FILE-0001', raw=True).decode().splitlines()
assert sequence[0].startswith('>SYNTH-SAMPLE-0001') and set(sequence[1]) <= set('ACGT')
print('PASS: synthetic repository metadata and FASTA download')

health = call('/protein-paint/healthcheck')
assert health['dsSummary']['failed'] == 0 and health['dsSummary']['done'] == 1
pp = {'genome': 'hg38', 'dslabel': 'MMRF', 'filter0': cohort_filter}
samples = call('/protein-paint/termdb/singlecellSamples', pp)['samples']
assert {s['sample'] for s in samples} == {c['sample_id'] for c in female}
converted = call('/protein-paint/termdb', {**pp, 'for': 'convertSampleId', 'inputs': [c['sample_id'] for c in female]})['mapping']
assert set(converted.values()) == {c['case_id'] for c in female}
genes = call('/protein-paint/termdb/topMutatedGenes', pp)['genes']
expected = {}
for variant in variants:
    if variant['case_id'] in {c['case_id'] for c in female}:
        expected.setdefault(variant['symbol'], set()).add(variant['sample_id'])
assert {g['gene']: g['mutationStat'][0]['count'] for g in genes} == {g: len(s) for g, s in expected.items()}
print('PASS: ProteinPaint cohort, sample-to-case conversion, and mutation counts match Gen3')
chart = call('/analysis/v0/genomic/gene_frequency_chart', {'cohort_filter': cohort_filter})
table = call('/analysis/v0/genomic/gene_table', {'cohort_filter': cohort_filter})
assert {g['symbol']: g['numCases'] for g in chart['data']} == {g: len(v) for g, v in expected.items()}
assert {g['symbol']: g['case_count'] for g in table['genes']} == {g: len(v) for g, v in expected.items()}
for path, items, count_field in [('gene_frequency_chart', 'data', 'numCases'), ('gene_table', 'genes', 'case_count')]:
    filtered = call('/analysis/v0/genomic/' + path, {'cohort_filter': cohort_filter, 'gene_filter': {'in': {'is_cancer_gene_census': ['true']}}})
    assert {g['symbol']: g[count_field] for g in filtered[items]} == {g: len(v) for g, v in expected.items()}
assert all(g['ssm_count'] > 0 for g in table['genes'])

mutations = call('/analysis/v0/genomic/ssm_table', {'cohort_filter': cohort_filter})
assert mutations['ssmsTotal'] == sum(v['case_id'] in {c['case_id'] for c in female} for v in variants)
assert all(s['score'] == 1 for s in mutations['ssms'])
print('PASS: real analysis gene/mutation totals match independently generated cohort variants')


seq = call('/protein-paint/ntseq', {'genome': 'hg38', 'coord': 'chr17:30000-30020'})['seq']
assert len(seq) == 21 and set(seq) <= set('ACGT')
single = call('/protein-paint/termdb/singlecellData', {**pp, 'sample': {'sID': female[0]['sample_id']}, 'plots': ['UMAP']})
assert single.get('plots') and len(single['plots'][0]['noExpCells']) == 80
scatter = call('/protein-paint/termdb/sampleScatter', {**pp, 'plotName': 'Bulk RNA-seq UMAP'})
assert scatter.get('result')
print('PASS: synthetic reference sequence, single-cell UMAP, and bulk UMAP')

survival = call('/analysis/v0/survival/', {'filters': [cohort_filter]})
assert survival['results']
assert {d['id'] for d in survival['results'][0]['donors']} == {c['case_id'] for c in female}
print('PASS: real analysis service returns survival for the selected synthetic cohort')
groups = [{'name': gender, 'values': [{'sampleId': i + 1} for i, c in enumerate(cases) if c['gender'] == gender]} for gender in ('female', 'male')]
de = {'genome': 'hg38', 'dslabel': 'MMRF', 'samplelst': {'groups': groups}, 'method': 'wilcoxon',
      'min_count': 10, 'min_total_count': 15, 'cpm_cutoff': 0,
      'volcanoRender': {'pixelWidth': 600, 'pixelHeight': 400, 'significanceThresholds': {'pValueCutoff': 1.3, 'pValueType': 'adjusted', 'foldChangeCutoff': 1}}}
assert call('/protein-paint/termdb/DE', {**de, 'preAnalysis': True})['data'] == {'female': len(female), 'male': len(cases) - len(female)}
result = call('/protein-paint/termdb/DE', de)
assert result['data']['totalRows'] == 5 and result['data']['volcanoPng']
print('PASS: actual differential expression calculation and volcano rendering on random counts')
print('Sandbox integration smoke checks passed')

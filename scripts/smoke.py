"""Exercise real sandbox APIs and cross-service synthetic ID consistency."""
import argparse
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
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
            assert 'Set-Cookie' not in response.headers, 'Sandbox must not replace localhost login cookies'
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
assert {s['sample'] for s in samples if s['sample'] != 'combined'} == {c['sample_id'] for c in female}
assert any(s['sample'] == 'combined' for s in samples)
all_samples = call('/protein-paint/termdb/singlecellSamples?' + urllib.parse.urlencode({'genome': 'hg38', 'dslabel': 'MMRF', 'filter0': '{}'}))['samples']
assert {s['sample'] for s in all_samples if s['sample'] != 'combined'} == {c['sample_id'] for c in cases}
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
meta_query = {**pp,
    'singleCellPlot': {'name': 'Meta analysis', 'sample': {'sID': 'combined', 'isMetaResult': True}},
    'canvasSettings': {'cutoff': 1000, 'width': 400, 'height': 400, 'radius': 2, 'devicePixelRatio': 1, 'startColor': '#d3d3d3', 'stopColor': '#ff0000'}}
single = call('/protein-paint/termdb/singleCellPlots', meta_query)
assert single['result']['Default']['totalSampleCount'] == len(female) * 80
assert single['result']['Default']['src']
colored = call('/protein-paint/termdb/singleCellPlots', {**meta_query, 'colorTW': {'$id': 'synthetic_myc',
    'term': {'type': 'singleCellGeneExpression', 'name': 'MYC', 'gene': 'MYC', 'sample': {'sID': 'combined', 'isMetaResult': True}, 'plot': 'Meta analysis'},
    'q': {'mode': 'continuous'}}})
assert colored['result']['Default']['totalSampleCount'] == len(female) * 80
assert colored['result']['Default']['src']
scatter = call('/protein-paint/termdb/sampleScatter', {**pp, 'plotName': 'Bulk RNA-seq UMAP'})
assert {s['sample'] for group in scatter['result'].values() for s in group['samples']} == {c['sample_id'] for c in female}
empty = call('/protein-paint/termdb/sampleScatter', {**pp, 'filter0': {'in': {'case_id': ['SYNTH-CASE-NO-MATCH']}}, 'plotName': 'Bulk RNA-seq UMAP'})
assert not any(group['samples'] for group in empty['result'].values())
config = call('/protein-paint/termdb/config?genome=hg38&dslabel=MMRF')['termdbConfig']
assert set(config['supportedChartTypes']['']) == {'summaryInput', 'survival', 'DA'}
for alias in ('MYC', 'c-Myc', 'ENSG00000136997', 'ENST00000621592', 'NM_002467'):
    lookup = call('/protein-paint/genelookup', {'genome': 'hg38', 'input': alias, 'deep': True})
    assert lookup['gmlst'][0]['name'] == 'MYC', alias
print('PASS: synthetic reference, filtered meta-analysis UMAP, bulk UMAP, curated chart menu and MYC aliases')

survival = call('/analysis/v0/survival/', {'filters': [cohort_filter]})
assert survival['results']
assert {d['id'] for d in survival['results'][0]['donors']} == {c['case_id'] for c in female}
print('PASS: real analysis service returns survival for the selected synthetic cohort')
female_case_ids = {c['case_id'] for c in female}
for symbol, mutated_samples in expected.items():
    mutated_case_ids = {v['case_id'] for v in variants if v['symbol'] == symbol and v['case_id'] in female_case_ids}
    comparison = call('/analysis/v0/survival/compare_genomic', {'case_filter': cohort_filter, 'filter': {}, 'symbol': symbol, 'type': 'gene'})
    assert len(comparison['results']) == 2, (symbol, comparison)
    assert {d['id'] for d in comparison['results'][0]['donors']} == female_case_ids - mutated_case_ids
    assert {d['id'] for d in comparison['results'][1]['donors']} == mutated_case_ids
print('PASS: gene-survival curves include the exact mutated and unmutated cases for all six fixture genes')
for expression, selected in [
    ({'>=': {'demographic.days_to_death': 1000}}, [c for c in cases if c['days_to_death'] is not None and c['days_to_death'] >= 1000]),
    ({'in': {'files.data_format': ['FASTA']}}, cases),
]:
    result = call('/guppy/graphql', {'query': query if 'CaseCentric' in query else 'query($filter:JSON){CaseCentric_case_centric(first:1000,filter:$filter){case_id}}', 'variables': {'filter': expression}})
    assert {c['case_id'] for c in result['data']['CaseCentric_case_centric']} == {c['case_id'] for c in selected}
    result = call('/protein-paint/termdb/singlecellSamples', {'genome': 'hg38', 'dslabel': 'MMRF', 'filter0': expression})
    assert {s['sample'] for s in result['samples'] if s['sample'] != 'combined'} == {c['sample_id'] for c in selected}
print('PASS: nullable clinical and file-facet cohorts match across real Guppy and ProteinPaint')

if len(cases) >= 1000:
    demographic_groups = []
    for gender, race in [('male', 'white'), ('female', 'black or african american')]:
        selection = {'and': [{'in': {'demographic.gender': [gender]}}, {'in': {'demographic.race': [race]}}]}
        expected_cases = {c['case_id'] for c in cases if c['gender'] == gender and c['race'] == race}
        curve = call('/analysis/v0/survival/', {'filters': [selection]})['results'][0]
        assert len(expected_cases) >= 100
        assert {d['id'] for d in curve['donors']} == expected_cases
        demographic_groups.append(selection)
    compared = call('/analysis/v0/survival/', {'filters': demographic_groups})
    assert len(compared['results']) == 2 and all(len(curve['donors']) >= 100 for curve in compared['results'])
    print('PASS: two-filter demographic cohorts retain >=100 survival cases per curve')

# Diagnosis age is an API value in years; use exactly matching half-open bins.
age_field = 'diagnoses.age_at_diagnosis'
comparison = call('/analysis/v0/compare/facets', {
    'doc_type': 'case_centric', 'cohort1': {}, 'cohort2': {},
    'facets': [age_field], 'interval': {age_field: 10},
})
for bucket in comparison['cohort1']['facets'][age_field]['buckets']:
    lower, upper = bucket['key']
    expected = {c['case_id'] for c in cases if lower <= c['diagnoses'][0]['age_at_diagnosis'] < upper}
    assert bucket['count'] == len(expected)
    data = call('/guppy/graphql', {
        'query': 'query($filter:JSON){CaseCentric_case_centric(first:1000,filter:$filter){case_id}}',
        'variables': {'filter': {'and': [{'>=': {age_field: lower}}, {'<': {age_field: upper}}]}},
    })['data']['CaseCentric_case_centric']
    assert {c['case_id'] for c in data} == expected
print('PASS: ten-year age comparison buckets and cohort filters return identical cases')

groups = [{'name': gender, 'values': [{'sampleId': i + 1} for i, c in enumerate(cases) if c['gender'] == gender]} for gender in ('female', 'male')]
de = {'genome': 'hg38', 'dslabel': 'MMRF', 'samplelst': {'groups': groups}, 'method': 'wilcoxon',
      'min_count': 10, 'min_total_count': 15, 'cpm_cutoff': 0,
      'volcanoRender': {'pixelWidth': 600, 'pixelHeight': 400, 'significanceThresholds': {'pValueCutoff': 1.3, 'pValueType': 'adjusted', 'foldChangeCutoff': 1}}}
assert call('/protein-paint/termdb/DE', {**de, 'preAnalysis': True})['data'] == {'female': len(female), 'male': len(cases) - len(female)}
result = call('/protein-paint/termdb/DE', de)
assert result['data']['totalRows'] == len({v['symbol'] for v in variants}) and result['data']['volcanoPng']
pseudobulk = call('/protein-paint/termdb/DE', {**de, 'pseudobulk': {'assay': 'geneExpression', 'memberId': 'Cell Type', 'category': 'Plasma'}})
assert pseudobulk['data']['totalRows'] == len({v['symbol'] for v in variants}) and pseudobulk['data']['volcanoPng']
print('PASS: actual bulk and single-cell pseudobulk differential expression and volcano rendering')
print('Sandbox integration smoke checks passed')

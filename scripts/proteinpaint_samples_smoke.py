"""Verify ProteinPaint sample lists, ID conversion, and selected-cohort tracks."""
import argparse
import json
from pathlib import Path
import urllib.request
from sandbox_connection import connection

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--origin', default='http://127.0.0.1:3080')
parser.add_argument('--access-file')
args = parser.parse_args()
access_headers, opener = connection(args.origin, args.access_file)
root = Path(__file__).resolve().parents[1]
cases = json.loads((root / 'generated/cases.json').read_text())
variants = json.loads((root / 'generated/variants.json').read_text())
base = {'genome': 'hg38', 'dslabel': 'MMRF'}
region = [{'chr': 'chr12', 'start': 10000, 'stop': 12000, 'width': 800}]


def call(path, payload, duplicate=False):
    request = urllib.request.Request(args.origin + '/protein-paint/' + path,
        data=json.dumps({**base, **payload}).encode(),
        headers={**access_headers, 'Content-Type': 'application/json, application/json' if duplicate else 'application/json'})
    with opener.open(request, timeout=90) as response:
        result = json.load(response)
    assert not result.get('error'), result
    return result


for selected in [cases, [c for c in cases if c['gender'] == 'female']]:
    filter0 = {'and': [{'in': {'case_id': [c['case_id'] for c in selected]}}]}
    allowed_cases = {c['case_id'] for c in selected}
    expected = {v['sample_id'] for v in variants if v['symbol'] == 'KRAS' and v['case_id'] in allowed_cases}
    query = {'filter0': filter0, 'variant2samples': 1, 'rglst': region}
    listing = call('mds3', {**query, 'get': 'samples'}, duplicate=True)['variant2samples']['samples']
    assert {s['sample_id'] for s in listing} == expected
    summary = call('mds3', {**query, 'get': 'summary', 'twLst': [
        {'term': {'id': 'gender', 'name': 'Gender', 'type': 'categorical'}, 'q': {}, '$id': 'gender'}]}, duplicate=True)
    assert summary['variant2samples']['summary']
    track_query = {'filter0': filter0, 'forTrack': 1, 'skewer': 1, 'rglst': region}
    track = call('mds3', track_query, duplicate=True)
    assert track['sampleTotalNumber'] == len(expected)
    hotspot = max(track['skewer'], key=lambda v: v['occurrence'])
    expected_carriers = {v['sample_id'] for v in variants
        if v['ssm_id'] == hotspot['vcf_id'] and v['case_id'] in allowed_cases}
    carriers = call('mds3', {'filter0': filter0, 'variant2samples': 1, 'get': 'samples',
        'ssm_id_lst': hotspot['ssm_id']}, duplicate=True)['variant2samples']['samples']
    assert {s['sample_id'] for s in carriers} == expected_carriers
    mapping = call('termdb', {'for': 'convertSampleId', 'inputs': sorted(expected_carriers)})['mapping']
    expected_case_ids = {c['case_id'] for c in selected if c['sample_id'] in expected_carriers}
    assert set(mapping.values()) == expected_case_ids
    # Match the scalar case-ID filter emitted by the Virtual Lab save-cohort wrapper.
    cohort = {'and': [{'in': {'case_id': sorted(mapping.values())}}]}
    rebuilt = call('mds3', {**track_query, 'filter0': cohort}, duplicate=True)
    assert rebuilt['sampleTotalNumber'] == len(expected_carriers)
    assert next(v for v in rebuilt['skewer'] if v['ssm_id'] == hotspot['ssm_id'])['occurrence'] == len(expected_carriers)
    print(f'PASS: {len(expected)} KRAS samples, summary, hotspot list, and {len(expected_carriers)}-case cohort reload')

empty = call('mds3', {'filter0': {'and': [{'in': {'case_id': ['SYNTH-CASE-NO-MATCH']}}]},
    'variant2samples': 1, 'get': 'samples', 'rglst': region}, duplicate=True)
assert empty['variant2samples']['samples'] == []
print('PASS: an empty cohort never falls back to all samples')

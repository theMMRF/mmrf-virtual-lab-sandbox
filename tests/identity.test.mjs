import test from 'node:test';
import assert from 'node:assert/strict';
import { createIdentity } from '../identity/token.mjs';
import { bridgePayload, matches } from '../identity/cohorts.mjs';

test('ephemeral identities reject real, malformed, changed, and other-instance tokens', () => {
  const one = createIdentity();
  const two = createIdentity();
  const token = one.issue();
  assert.equal(one.valid(token), true);
  assert.equal(two.valid(token), false);
  assert.equal(one.valid(undefined), false);
  assert.equal(one.valid('not-a-token'), false);
  const parts = token.split('.');
  parts[1] = Buffer.from(JSON.stringify({ iss: 'mmrf-synthetic-sandbox', exp: 9999999999 })).toString('base64url');
  assert.equal(one.valid(parts.join('.')), false);
});

test('cohort bridge keeps nested case selection and ProteinPaint filters in intersection', () => {
  const cases = [
    { case_id: 'SYNTH-CASE-0001', gender: 'female', age_at_index: 50 },
    { case_id: 'SYNTH-CASE-0002', gender: 'male', age_at_index: 70 },
    { case_id: 'SYNTH-CASE-0003', gender: 'female', age_at_index: 80 },
  ];
  const expression = { and: [{ in: { gender: ['female'] } }, { '>=': { age_at_index: 60 } }] };
  assert.equal(matches(cases[0], expression), false);
  assert.equal(matches(cases[2], { in: { 'cases.case_id': ['SYNTH-CASE-0003'] } }), true);
  const original = { type: 'tvslst', in: true, join: 'and', lst: [{ type: 'tvs' }] };
  const result = bridgePayload({ filter0: expression, filter: original }, cases);
  assert.deepEqual(result.filter.lst[0].tvs.term.values.synthetic.list, [{ sample: 3 }]);
  assert.equal(result.filter.lst[1], original);
  assert.equal('filter0' in result, false);
  assert.throws(() => matches(cases[0], { unknown: {} }), /Unsupported/);
  assert.throws(() => matches(cases[0], { in: { nonexistent: ['x'] } }), /Unsupported/);
  const empty = bridgePayload({ filter0: { in: { gender: ['absent'] } } }, cases);
  assert.deepEqual(empty.filter.lst[0].tvs.term.values.synthetic.list, []);
});

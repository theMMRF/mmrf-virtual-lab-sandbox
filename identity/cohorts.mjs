function values(record, path) {
  const parts = path.replace(/^cases\./, '').split('.');
  let current = [record];
  for (const part of parts) current = current.flatMap(value => Array.isArray(value) ? value.flatMap(v => v?.[part] ?? []) : value?.[part] ?? []);
  return current.flat(Infinity);
}

export function matches(record, expression) {
  if (expression == null || Object.keys(expression).length === 0) return true;
  if (typeof expression !== 'object' || Array.isArray(expression)) throw new Error('Unsupported cohort filter');
  return Object.entries(expression).every(([operator, operands]) => {
    const op = operator.toLowerCase();
    if (op === 'and' || op === 'or') {
      if (!Array.isArray(operands)) throw new Error('Invalid logical cohort filter');
      return op === 'and' ? operands.every(v => matches(record, v)) : operands.some(v => matches(record, v));
    }
    if (op === 'not') return !matches(record, operands);
    if (!['in', 'exclude', '=', '!=', '>', '>=', '<', '<='].includes(op)) throw new Error(`Unsupported cohort operator: ${operator}`);
    return Object.entries(operands).every(([field, wanted]) => {
      const actual = values(record, field);
      if (!actual.length) throw new Error(`Unsupported synthetic cohort field: ${field}`);
      const choices = Array.isArray(wanted) ? wanted : [wanted];
      if (op === 'in' || op === '=') return actual.some(v => choices.includes(v));
      if (op === 'exclude' || op === '!=') return !actual.some(v => choices.includes(v));
      return actual.some(v => ({ '>': v > wanted, '>=': v >= wanted, '<': v < wanted, '<=': v <= wanted })[op]);
    });
  });
}

export function bridgePayload(input, cases) {
  if (input.samplelst?.groups) input = {...input, samplelst: {...input.samplelst, groups: input.samplelst.groups.map(group => bridgePayload(group, cases))}};
  if (!input.filter0) return input;
  const expression = typeof input.filter0 === 'string' ? JSON.parse(input.filter0) : input.filter0;
  const samples = cases.flatMap((record, index) => matches(record, expression) ? [{ sample: index + 1 }] : []);
  const scope = { type: 'tvs', tvs: { term: { type: 'samplelst', values: { synthetic: { key: 'synthetic', label: 'Synthetic cohort', list: samples } } } } };
  const filter = typeof input.filter === 'string' ? JSON.parse(input.filter) : input.filter;
  const merged = { type: 'tvslst', in: true, join: 'and', lst: [scope, ...(filter?.lst?.length ? [filter] : [])] };
  const result = { ...input, filter: merged };
  delete result.filter0;
  return result;
}

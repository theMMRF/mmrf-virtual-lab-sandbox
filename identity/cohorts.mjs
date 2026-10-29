function values(record, path) {
  const parts = path.replace(/^cases\./, '').split('.');
  let current = [record];
  const read = (value, part) => value != null && Object.hasOwn(value, part) ? [value[part]] : [];
  for (const part of parts) current = current.flatMap(value => Array.isArray(value) ? value.flatMap(v => read(v, part)) : read(value, part));
  return current.flat(Infinity);
}

export function matches(record, expression, known) {
  if (expression == null || Object.keys(expression).length === 0) return true;
  if (typeof expression !== 'object' || Array.isArray(expression)) throw new Error('Unsupported cohort filter');
  return Object.entries(expression).every(([operator, operands]) => {
    const op = operator.toLowerCase();
    if (op === 'and' || op === 'or') {
      if (!Array.isArray(operands)) throw new Error('Invalid logical cohort filter');
      return op === 'and' ? operands.every(v => matches(record, v, known)) : operands.some(v => matches(record, v, known));
    }
    if (op === 'not') return !matches(record, operands, known);
    if (!['in', 'exclude', '=', '!=', '>', '>=', '<', '<='].includes(op)) throw new Error(`Unsupported cohort operator: ${operator}`);
    return Object.entries(operands).every(([field, wanted]) => {
      const actual = values(record, field);
      if (!actual.length && !known?.(field)) throw new Error(`Unsupported synthetic cohort field: ${field}`);
      // Legacy ProteinPaint cohorts store mapped sample objects. Real Guppy /
      // Elasticsearch accepts this form; preserve it in the local PP bridge too.
      const choices = (Array.isArray(wanted) ? wanted : [wanted]).map(value =>
        ['case_id', 'cases.case_id'].includes(field) && value != null &&
        typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === 1 &&
        Object.hasOwn(value, 'cases.case_id') && typeof value['cases.case_id'] === 'string'
          ? value['cases.case_id'] : value);
      if (op === 'in' || op === '=') return actual.some(v => choices.includes(v));
      if (op === 'exclude' || op === '!=') return !actual.some(v => choices.includes(v));
      return actual.some(v => v != null && ({ '>': v > wanted, '>=': v >= wanted, '<': v < wanted, '<=': v <= wanted })[op]);
    });
  });
}

export function bridgePayload(input, cases) {
  if (input.samplelst?.groups) input = {...input, samplelst: {...input.samplelst, groups: input.samplelst.groups.map(group => bridgePayload(group, cases))}};
  if (!input.filter0) return input;
  const expression = typeof input.filter0 === 'string' ? JSON.parse(input.filter0) : input.filter0;
  const fields = new Map();
  const known = field => {
    if (!fields.has(field)) fields.set(field, cases.some(record => values(record, field).length > 0));
    return fields.get(field);
  };
  const samples = cases.flatMap((record, index) => matches(record, expression, known) ? [{ sample: index + 1 }] : []);
  const scope = { type: 'tvs', tvs: { term: { type: 'samplelst', values: { synthetic: { key: 'synthetic', label: 'Synthetic cohort', list: samples } } } } };
  const filter = typeof input.filter === 'string' ? JSON.parse(input.filter) : input.filter;
  const native = filter?.type === 'tvslst' && filter.lst?.length === 0 && filter.in !== false ? null : filter;
  const merged = { type: 'tvslst', in: true, join: 'and', lst: [scope, ...(native ? [native] : [])] };
  const result = { ...input, filter: merged };
  delete result.filter0;
  return result;
}

# Developer API examples

Use the loopback gateway at `http://localhost:3080` (or an explicitly local
Kubernetes port-forward). It supplies a fresh synthetic identity automatically;
there is no credentials-file setup. Do not point these examples at a real commons.
The backing services are real public Guppy, analysis and ProteinPaint servers.

## Select a cohort

```sh
curl -fsS http://localhost:3080/guppy/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"query($filter:JSON){CaseCentric_case_centric(first:1000,filter:$filter){case_id samples{sample_id}}}","variables":{"filter":{"in":{"demographic.gender":["female"]}}}}'
```

The default seed returns 500 of 1,000 cases. Cohort creation/naming and the currently
selected cohort are managed by the existing frontend's browser state. A language
interface embedded in that frontend should use its cohort actions/selectors;
`/analysis/v0/cohorts/query` is a query endpoint, not a new cohort-storage API.
This launcher does not add a persistence API or implement the language interface.

## Carry the same selection into ProteinPaint

```sh
curl -fsS http://localhost:3080/protein-paint/termdb/topMutatedGenes \
  -H 'Content-Type: application/json' \
  -d '{"genome":"hg38","dslabel":"MMRF","filter0":{"in":{"demographic.gender":["female"]}}}'
```

The gateway translates `filter0` into native ProteinPaint sample filters and
intersects an existing native filter. Expanded GET cohort queries become JSON
POSTs to avoid request-line limits; this remains a read operation. It also translates sample-group cohort
filters for differential expression. The generated `SYNTH-SAMPLE-*` names map
back to `SYNTH-CASE-*` using ProteinPaint's `convertSampleId` termdb action.
Synthetic gene search supports KRAS, NRAS, TP53, BRAF, DIS3 and MYC. The `hg38` key
is a compatibility key for a fabricated reference, not real genome data.

## Query files and survival

```sh
curl -fsS http://localhost:3080/guppy/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"{File_file(first:10){file_id file_name data_type data_format cases{case_id}}}"}'
curl -fsS http://localhost:3080/sandbox/files/SYNTH-FILE-0001
curl -fsS http://localhost:3080/analysis/v0/survival/ \
  -H 'Content-Type: application/json' \
  -d '{"filters":[{"in":{"demographic.gender":["female"]}}]}'
```

Only generated FASTA files can be downloaded. `scripts/smoke.py` contains working
examples for gene-frequency tables, single-cell and bulk UMAP, reference sequence,
and differential expression. `config/cohort-fields.json` lists generated clinical
field shapes. Operators `and`, `or`, `not`, `in`, `exclude`, `=`, `!=`, `>`, `>=`,
`<` and `<=` are supported by the bridge; unsupported expressions fail explicitly.

## Change a public service locally

Edit its disposable `.sources/<service>` checkout and run `docker compose build
<service>` followed by `docker compose up -d --wait`. Source contexts are ignored
and are not vendored into this repository. The source-fetch helper refuses to
overwrite edits, so use Compose directly while editing. Keep durable application
changes in that service's own repository/PR and update `sources.json` to its
public commit for reproducible builds. Never replace a source URL with a private
repository for a shareable challenge build.

## Diagnosis age units

`diagnoses.age_at_diagnosis` is in **years**, matching the operator-confirmed
current MMRF API contract. Do not divide this value by 365.25. The inherited
dictionary wording was day-based; its clarification and the frontend correction
are separate PRs: [dictionary #7](https://github.com/theMMRF/mmrf_dictionary/pull/7)
and [frontend #42](https://github.com/theMMRF/mmrf-data-commons/pull/42).
The sandbox pins a frontend containing that correction. Comparison bins use
`[40, 50)` for ages 40 through just below 50; follow-up/survival durations retain
their own day-based API fields. No records are converted or reindexed.

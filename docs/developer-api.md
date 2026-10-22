# Developer API examples

Examples use the local gateway at `http://localhost:3080`, which supplies the
synthetic session and routes requests to Guppy, Analysis, and ProteinPaint.

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

Only tiny generated FASTA/BAM/FASTQ/TSV/VCF/CSV test files can be downloaded.
The website exports filtered manifests, sample sheets and metadata without S3.
There is no Gen3 CLI transfer/credential service. `scripts/smoke.py` contains working
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
commit for reproducible builds.

## Data units

`diagnoses.age_at_diagnosis` is in years. Follow-up and survival duration fields
use days. Comparison bins such as `[40, 50)` include ages 40 through just below 50.

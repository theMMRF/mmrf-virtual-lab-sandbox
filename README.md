# MMRF Virtual Lab Sandbox

A synthetic-only developer environment for the MMRF Virtual Lab. The frontend,
Guppy, Gen3 analysis service, and ProteinPaint remain separate projects. This
repository supplies their sandbox configuration, generated fixtures, disposable
identity service, Docker Compose launcher, Helm chart, and Terraform for a new
dedicated AWS account.

No Gen3 credentials, patient-data exports, private repositories, production
images, AWS account access, or private deployment configuration are required for
local development. Fixture values are generated from a seed; this is not a
de-identification pipeline. Scientific outputs have no biological meaning.

## Local startup

Requirements: Git, Python 3.9+, and Docker with Compose 2.17+, at least 12 GB of
available Docker memory and 20 GB of disk. The public ProteinPaint base is amd64;
Docker Desktop runs it through emulation on Apple Silicon.

```sh
python3 scripts/fetch_sources.py
python3 synthetic/generate.py
docker compose build
docker compose up -d --wait --wait-timeout 300
python3 scripts/smoke.py
```

Open <http://localhost:3080>. The sandbox establishes a disposable synthetic
developer session automatically. Do not enter or mount real credentials.
Only the gateway is published, on loopback; backing services have no host ports.
The gateway accepts only its own service names or loopback as upstreams.

```sh
# Stop and preserve the disposable synthetic search index.
docker compose down
# Fully discard the sandbox's generated search volume.
docker compose down --volumes
```

The pinned public source commits are in `sources.json`. `scripts/fetch_sources.py`
checks out clean detached copies into ignored `.sources/` directories; it refuses
to overwrite edited copies. To develop an existing service, edit its source
checkout and rebuild that service, or run its normal development command against
the sandbox's local API. No application source is vendored in this repository.

For repeatable browser tests and screenshots (a fresh headless Chromium profile):

```sh
npm ci
npx playwright install chromium
npm run test:ui
```

Results are written to ignored `screenshots/`. The UI test creates a demographic
cohort and verifies its mutation counts against the generator output.

For the difference from your regular frontend workflow and suggested manual checks,
see [local development modes](docs/local-development.md).

## Fixtures and contracts

```sh
python3 synthetic/generate.py --cases 1000 --seed 42
node --test tests/*.test.mjs
python3 -m unittest discover -s tests -p 'test_*.py'
```

`SYNTH-CASE-0001`, `SYNTH-SAMPLE-0001`, and `SYNTH-FILE-0001` identify the same
generated case throughout Gen3, ProteinPaint, repository metadata, and generated
test files. The generator accepts a seed and count, never a data input. Gene
symbols are public reference identifiers, but gene models, coordinates, variants,
reference sequence, expression, survival, UMAP coordinates, and cell values are
fabricated. The fixture genes are KRAS, NRAS, TP53, BRAF, DIS3 and MYC; use those
symbols when testing gene search. The `hg38` dataset key is retained for frontend compatibility; these
fixtures do **not** represent the real human genome.

The default seed (42) has 1,000 cases split across two projects, 2,908 mutation occurrences
sharing 48 invented variants across six genes, and 80,000 synthetic single cells.
File facets span WGS, WXS, RNA-Seq and scRNA-Seq, with FASTA, BAM, FASTQ, TSV, VCF
and CSV test files and multiple categories/workflows. Recurring hotspots and
mutation classes make cohort comparisons useful; they are not clinical models.
Single-cell coordinates use irregular curved subclusters, not measured embeddings. Balanced demographic categories keep ordinary
sex/race cohorts above the existing ten-case survival threshold. These are
demonstration choices, not estimates of real demographics or mutation prevalence.
MYC also resolves through c-Myc, ENSG00000136997, ENST00000621592, and NM_002467.

The ProteinPaint image generates indexed BCF and CNV files, a term database,
synthetic gene tracks, bulk expression/count matrices, bulk UMAP, and single-cell
UMAP/expression files. Historical frontend demonstration fixture values are
replaced in the disposable image build, and sandbox builds disable demo-mode
URLs and analytics. The original repositories are not changed by sanitization.

The sandbox gateway bridges Gen3 cohort filters into native ProteinPaint sample
filters. Unsupported filter operators fail explicitly. Existing production
authentication code is used unchanged with an isolated signing key created in
memory at startup. A sandbox token cannot authenticate to the real commons.
The identity service implements a small synthetic Fence/Arborist contract, not a
general-purpose identity provider. Cohorts persist in the frontend's browser
storage; all developers share the synthetic identity.

## Deployment and handoff

See [AWS deployment](docs/aws-deployment.md) for the operator-run EKS launcher:
`init`, `check`, `build`, `deploy`, `status`, and `destroy`. It provisions a
CloudFront HTTPS hostname in front of a private ALB and a password-protected
entry, without requiring a domain or certificate. AWS image builds use separate
local tags; normal Compose behavior stays unchanged. The launcher automates
image publication, dedicated kubeconfig/Secret creation, Helm deployment and
state-owned teardown. Only the operator runs its AWS commands. Local Kubernetes testing
uses the same chart with a separate kind cluster and kubeconfig; see
[local Kubernetes](docs/local-kubernetes.md) for the amd64 requirement.

The Terraform tests use a mocked AWS provider. Passing them or a local Kubernetes
deployment is not proof that a particular AWS account has the required quotas,
permissions, networking, or region availability. No AWS deployment has been
performed by this project preparation workflow.

See [component inventory](docs/component-inventory.md) for public/private
dependencies and [verification](docs/verification.md) for the actual test record.

See [developer API examples](docs/developer-api.md) for cohort selection,
ProteinPaint, file search/download and local service development.

## Hackathon boundary

This environment supports building a natural-language interface against existing
platform actions and APIs. The language interface, MCP servers, multi-agent
orchestration, and biomedical knowledge graph are challenge/future work, rather
than part of the environment launcher. Notebooks, file upload, real-data download,
and production identity federation are excluded. The repository browser downloads
only tiny generated test files; manifests and sample sheets work without S3 or
Gen3 CLI credentials. BAM fixtures contain a single fabricated unmapped read;
VCF repository fixtures are valid header-only examples. None is real assay data.

## Licenses

New sandbox code is Apache-2.0. Individual dependencies retain their own licenses.
ProteinPaint's public source has an **academic-use license**, not an unrestricted
open-source license. Review the upstream [ProteinPaint license](https://github.com/stjude/proteinpaint/blob/master/LICENSE)
for the intended event and any later use. The private `ppmmrf` code and history
are not copied or relicensed here.

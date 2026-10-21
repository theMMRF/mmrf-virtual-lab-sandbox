# Verification record

Checked 2026-10-21 on Apple Silicon with Docker Desktop. Local checks did not mount AWS profiles/credentials, call AWS APIs, or run a real
Terraform plan/apply. Existing automatic preview-image builds are separate. Real account
provisioning is explicitly an operator acceptance gate in the AWS runbook.

## Passed locally

- Seed-only generator determinism and case/sample/file/VCF/SQLite ID integrity.
- Ephemeral signing keys, invalid/tampered/cross-instance token rejection and
  intersection of Gen3 cohort selection with native ProteinPaint filtering.
- Production frontend container build from pinned public source with historical
  demo fixture scalars replaced and the synthetic presentation flag enabled.
- Clean Docker Compose build/start/health checks using real Elasticsearch, Guppy,
  Gen3 analysis and public ProteinPaint services. No Gen3 credential file.
- HTTP integration on the expanded default seed: 1,000 cases, female cohort 500,
  2,132 case-level variants across six genes, and 80,000 generated single cells.
  Case/sample membership and independently computed mutation totals agree across
  Guppy, analysis and ProteinPaint. Fabricated FASTA, reference sequence, survival,
  bulk expression, actual Wilcoxon differential expression and volcano rendering pass.
- Male/white and female/black demographic cohorts each contain 167 cases; both
  return full survival curves. All six gene-survival comparisons return the exact
  mutated and unmutated case sets. The synthetic demographic mapping matches
  the public analysis service's object-field survival queries. Generator checks
  also require at least ten mutated
  and ten unmutated cases for every fixture gene in each sex/race combination.
- Single-cell meta-analysis API returns exactly 40,000 cells for a 500-case female
  cohort, including MYC expression coloring. Actual pseudobulk differential
  expression runs against totals derived from those same generated cells.
- Uncolored bulk UMAP is checked against exact cohort membership and an empty
  cohort. A narrow version-checked correction to the public ProteinPaint server
  is required for this mode; see component-inventory.md.
- The curated Correlation chart allowlist and all MYC search examples are checked
  through the public API. Expanded GET cohort queries work without HTTP header/
  request-line overflow. API responses do not set localhost login cookies.
- Isolated Chromium creates a female/black cohort of 167 cases and verifies
  exact OncoMatrix counts, cohort-scoped repository files and bulk UMAP, a
  13,360-cell Meta analysis, the two visible Correlation buttons, Clinical Data
  Analysis survival, expression clustering, c-Myc search (57 variants), Genome
  Browser (52 KRAS-region variants), and Mutation Frequency survival. No failed
  local HTTP responses or uncaught page errors. A pre-existing localhost login
  cookie remains unchanged. Screenshots are saved under ignored screenshots/.
- Analytics environment/consent regression tests pass (22 tests). The synthetic
  browser run shows no tracking-consent modal, GA scripts, GA cookies or tracking
  requests, including with a previously accepted consent preference.
- Diagnosis age API comparisons use ten-year bins, with each bin's case IDs
  independently checked against the generator. The browser compares two
  demographic cohorts, checks every age bucket's counts, clicks a bucket to
  retrieve its exact members, and displays the clinical age histogram in years. Every clinical age bin is
  checked against generated cases, including those at the maximum age.
  The frontend fix has 24 regression tests; dictionary validation rules are
  unchanged by its separate description correction.
- Helm lint and rendering pass with the expanded-fixture configuration. Earlier
  Kubernetes server-side dry-run and startup tests used a separate kind cluster;
  frontend, identity, Guppy, analysis, Elasticsearch and the seed watcher started.
- Terraform formatting, validate and four mocked provider tests: isolated
  infrastructure, wrong-account role rejection, unrestricted/IPv6 API CIDR rejection.
- Gitleaks scan of publication files: no leaks found. Generated data, source
  contexts, node_modules, state, plans and kubeconfigs are excluded from Git.

The synthetic integration also exposed an existing Gen3 analysis gene-count
error (subtracting one from a score that already counts affected cases). The
pinned public source fix and its PR are listed in the handoff. The integration
checks compare both gene chart and gene table counts with generator output.

## Limits and remaining acceptance gates

- One frontend rebuild while the stack was running caused Docker to OOM-kill
  Elasticsearch. Restarting it recovered the existing synthetic volume. The
  local-development guide documents rebuilding with services stopped when Docker
  memory is constrained.

- A full local Helm rollout could not finish on the ARM node: the upstream
  ProteinPaint image is amd64-only. Compose ran it successfully through Docker
  emulation. The Terraform node is amd64. Test the entire chart on an amd64
  Kubernetes node; see local-kubernetes.md. The task-created kind cluster was
  removed after testing.
- NetworkPolicy enforcement, EKS permissions/quotas, ECR publication, AWS node
  startup, real-account costs and teardown have not been demonstrated locally.
- The smoke scripts are representative acceptance tests, not exhaustive tests of
  every tool option, statistical method or possible cohort expression. Unsupported
  cohort operators fail explicitly. Values have no clinical/scientific meaning.
- Notebooks, uploads, real downloads, production identity and the knowledge graph
  are excluded. Shared synthetic identity is appropriate only for this sandbox.
- CodeRabbit and GitHub CI status is reported separately on each PR. A passing
  local test does not establish a passing or completed hosted review.

## Reproduce

Run `scripts/start.sh`, then `npm ci`, `npx playwright install chromium`, and
`npm run test:ui`. PNGs and a local browser-error list are written under ignored
`screenshots/`. Use a fresh search volume when changing the fixture seed/count:
`docker compose down --volumes`, regenerate, rebuild fixture-bearing images and
start again. The seeder rejects mismatched fixture fingerprints.

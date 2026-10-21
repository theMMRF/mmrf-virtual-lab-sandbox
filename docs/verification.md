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
- HTTP integration: 60 cases, female cohort 30; identical case/sample membership
  across Guppy and ProteinPaint; exact independently computed mutation counts;
  fabricated FASTA download; synthetic reference sequence; single-cell UMAP with
  80 fabricated cells; bulk UMAP; selected-cohort survival; differential expression pre-analysis, actual Wilcoxon
  calculation and volcano rendering on random synthetic count matrices.
- Isolated Playwright Chromium: create the female cohort through Cohort Builder,
  carry it into OncoMatrix and check every gene count against the generated
  variants, browse repository metadata, view bulk UMAP, render an 80-cell single-cell
  UMAP, launch selected-cohort expression clustering, search TP53 in ProteinPaint,
  and render Mutation Frequency. No failed local HTTP responses or uncaught page errors in this test.
- Separate browser checks: expression clustering Submit renders a 60-sample,
  five-gene matrix; ProteinPaint TP53 search renders 25 fabricated variants.
- Helm lint and Kubernetes server-side dry-run against an isolated kind cluster.
  Actual local chart workloads for frontend, identity, Guppy, analysis,
  Elasticsearch and the seed watcher started successfully.
- Terraform formatting, validate and four mocked provider tests: isolated
  infrastructure, wrong-account role rejection, unrestricted/IPv6 API CIDR rejection.
- Gitleaks scan of publication files: no leaks found. Generated data, source
  contexts, node_modules, state, plans and kubeconfigs are excluded from Git.

The synthetic integration also exposed an existing Gen3 analysis gene-count
error (subtracting one from a score that already counts affected cases). The
pinned public source fix and its PR are listed in the handoff. The integration
checks compare both gene chart and gene table counts with generator output.

## Limits and remaining acceptance gates

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
